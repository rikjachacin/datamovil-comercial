from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
import os
import re
import warnings
import xml.etree.ElementTree as ET

import pandas as pd
import pyodbc
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = ValueError


SISCOR_CONFIG_PATH = Path(r"C:\SisCor\SisCor.exe.config")
SNAPSHOT_DIR = Path("data")
SAMPLE_FACTURAS_PATH = SNAPSHOT_DIR / "sample_facturas.csv"
SAMPLE_FACTURA_ITEMS_PATH = SNAPSHOT_DIR / "sample_factura_items.csv"
SNAPSHOT_KEY_PATH = SNAPSHOT_DIR / "snapshot.key"
DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"
EXCLUDED_COMMERCIAL_ZONES = ("PROVEEDORES",)
COMMERCIAL_DOCUMENT_TYPES = ("FC", "NC", "ND")


class SnapshotDataMissing(RuntimeError):
    """Raised when snapshot mode is enabled but exported data files are absent."""


@dataclass(frozen=True)
class SisCorConfig:
    server: str
    database: str
    username: str
    password: str
    driver: str = DEFAULT_DRIVER


def _parse_connection_string(value: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for raw_part in value.split(";"):
        if "=" not in raw_part:
            continue
        key, raw_value = raw_part.split("=", 1)
        parts[key.strip().lower()] = raw_value.strip()
    return parts


def _config_from_siscor_file(path: Path = SISCOR_CONFIG_PATH) -> SisCorConfig:
    tree = ET.parse(path)
    root = tree.getroot()
    connection_node = root.find(".//connectionStrings/add[@name='consultora']")
    if connection_node is None:
        raise RuntimeError("No se encontro la conexion 'consultora' en SisCor.exe.config.")

    parts = _parse_connection_string(connection_node.attrib.get("connectionString", ""))
    return SisCorConfig(
        server=parts.get("data source", ""),
        database=parts.get("database") or parts.get("initial catalog", ""),
        username=parts.get("user id") or parts.get("uid", ""),
        password=parts.get("password") or parts.get("pwd", ""),
    )


def get_config() -> SisCorConfig:
    try:
        secrets = st.secrets["siscor"]
        return SisCorConfig(
            server=secrets["server"],
            database=secrets["database"],
            username=secrets["username"],
            password=secrets["password"],
            driver=secrets.get("driver", DEFAULT_DRIVER),
        )
    except Exception:
        return _config_from_siscor_file()


def data_mode() -> str:
    env_mode = os.getenv("DATAMOVIL_DATA_MODE")
    if env_mode:
        return env_mode.lower()
    try:
        return str(st.secrets.get("data", {}).get("mode", "sql")).lower()
    except StreamlitSecretNotFoundError:
        return "sql"


def using_sample_snapshot() -> bool:
    return (
        data_mode() == "snapshot"
        and not (SNAPSHOT_DIR / "facturas.csv").exists()
        and not (SNAPSHOT_DIR / "facturas.csv.enc").exists()
        and SAMPLE_FACTURAS_PATH.exists()
    )


def _snapshot_key() -> str | None:
    env_key = os.getenv("DATAMOVIL_SNAPSHOT_KEY")
    if env_key:
        return env_key.strip()
    try:
        key = st.secrets.get("data", {}).get("snapshot_key")
        if key:
            return str(key).strip()
    except StreamlitSecretNotFoundError:
        pass
    if SNAPSHOT_KEY_PATH.exists():
        return SNAPSHOT_KEY_PATH.read_text(encoding="utf-8").strip()
    return None


def _read_snapshot_csv(filename: str, sample_path: Path) -> pd.DataFrame:
    csv_path = SNAPSHOT_DIR / filename
    if csv_path.exists():
        return pd.read_csv(csv_path)

    encrypted_path = SNAPSHOT_DIR / f"{filename}.enc"
    if encrypted_path.exists():
        if Fernet is None:
            raise SnapshotDataMissing("Falta instalar cryptography para leer el snapshot cifrado.")
        key = _snapshot_key()
        if not key:
            raise SnapshotDataMissing("Falta la clave data.snapshot_key para leer el snapshot cifrado.")
        try:
            data = Fernet(key.encode("utf-8")).decrypt(encrypted_path.read_bytes())
        except (InvalidToken, ValueError) as exc:
            raise SnapshotDataMissing("La clave data.snapshot_key no puede abrir el snapshot cifrado.") from exc
        return pd.read_csv(BytesIO(data))

    if sample_path.exists():
        return pd.read_csv(sample_path)

    raise SnapshotDataMissing(f"No se encontro data/{filename} para modo snapshot.")


def connection_string(config: SisCorConfig | None = None) -> str:
    cfg = config or get_config()
    return (
        f"DRIVER={{{cfg.driver}}};"
        f"SERVER={cfg.server};"
        f"DATABASE={cfg.database};"
        f"UID={cfg.username};"
        f"PWD={cfg.password};"
        "TrustServerCertificate=yes;"
    )


@st.cache_resource(show_spinner=False)
def get_connection() -> pyodbc.Connection:
    return pyodbc.connect(connection_string(), timeout=8)


@st.cache_data(ttl=300, show_spinner=False)
def read_sql(query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    with pyodbc.connect(connection_string(), timeout=8) as conn:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="pandas only supports SQLAlchemy connectable",
                category=UserWarning,
            )
            return pd.read_sql(query, conn, params=params)


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot_facturas() -> pd.DataFrame:
    df = _read_snapshot_csv("facturas.csv", SAMPLE_FACTURAS_PATH)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot_factura_items() -> pd.DataFrame:
    return _read_snapshot_csv("factura_items.csv", SAMPLE_FACTURA_ITEMS_PATH)


def _snapshot_filtered_facturas(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    zonas_filtro: tuple[str, ...] = (),
) -> pd.DataFrame:
    df = _snapshot_facturas().copy()
    df["zona"] = df["zona"].fillna("").replace("", "Sin zona")
    df = df[~df["zona"].isin(EXCLUDED_COMMERCIAL_ZONES)]
    df = df[df["tipo"].isin(COMMERCIAL_DOCUMENT_TYPES)]

    if fecha_desde:
        df = df[df["fecha"].dt.date >= pd.to_datetime(fecha_desde).date()]
    if fecha_hasta:
        df = df[df["fecha"].dt.date <= pd.to_datetime(fecha_hasta).date()]
    if zonas_filtro:
        df = df[df["zona"].isin(zonas_filtro)]

    sign = df["tipo"].map(lambda value: -1 if value == "NC" else 1)
    df["total_firmado"] = df["total"].astype(float) * sign
    df["subtotal_firmado"] = df["subtotal"].astype(float) * sign
    return df


def ping() -> pd.DataFrame:
    return read_sql(
        "SET NOCOUNT ON; SELECT DB_NAME() AS base, @@SERVERNAME AS servidor, GETDATE() AS fecha_servidor;"
    )


def month_options() -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_filtered_facturas()
        return pd.DataFrame(
            {
                "fecha_minima": [df["fecha"].dt.date.min()],
                "fecha_maxima": [df["fecha"].dt.date.max()],
            }
        )

    return read_sql(
        """
        SET NOCOUNT ON;
        SELECT
            MIN(CAST(fecha AS date)) AS fecha_minima,
            MAX(CAST(fecha AS date)) AS fecha_maxima
        FROM dbo.cli_factura
        WHERE ISNULL(Anulado, 0) = 0;
        """
    )


def _zona_filter(alias: str, zonas: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    if not zonas:
        return "", ()
    placeholders = ", ".join("?" for _ in zonas)
    return f" AND COALESCE(NULLIF({alias}.zona, ''), 'Sin zona') IN ({placeholders})", zonas


def _commercial_zone_filter(alias: str) -> str:
    excluded = ", ".join(f"'{zone}'" for zone in EXCLUDED_COMMERCIAL_ZONES)
    return f" AND COALESCE(NULLIF({alias}.zona, ''), 'Sin zona') NOT IN ({excluded})"


def _commercial_document_filter(alias: str) -> str:
    included = ", ".join(f"'{doc_type}'" for doc_type in COMMERCIAL_DOCUMENT_TYPES)
    return f" AND {alias}.tipo IN ({included})"


def _signed_total(alias: str, column: str = "total") -> str:
    return (
        f"CASE WHEN {alias}.tipo = 'NC' "
        f"THEN -CAST({alias}.{column} AS decimal(18, 2)) "
        f"ELSE CAST({alias}.{column} AS decimal(18, 2)) END"
    )


def zonas() -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_filtered_facturas()
        return pd.DataFrame({"zona": sorted(df["zona"].dropna().unique())})

    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT DISTINCT
            COALESCE(NULLIF(zona, ''), 'Sin zona') AS zona
        FROM dbo.cli_factura
        WHERE ISNULL(Anulado, 0) = 0
          {_commercial_zone_filter("dbo.cli_factura")}
          {_commercial_document_filter("dbo.cli_factura")}
        ORDER BY zona;
        """
    )


def kpis(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = ()) -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_filtered_facturas(fecha_desde, fecha_hasta, zonas_filtro)
        total = df["total_firmado"].sum()
        return pd.DataFrame(
            {
                "comprobantes": [len(df)],
                "clientes": [df["id_cliente"].nunique()],
                "total": [total],
                "subtotal": [df["subtotal_firmado"].sum()],
                "ticket_promedio": [total / len(df) if len(df) else 0],
            }
        )

    zona_sql, zona_params = _zona_filter("f", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            COUNT(*) AS comprobantes,
            COUNT(DISTINCT f.id_cliente) AS clientes,
            SUM({_signed_total("f", "total")}) AS total,
            SUM({_signed_total("f", "subtotal")}) AS subtotal,
            AVG({_signed_total("f", "total")}) AS ticket_promedio
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql};
        """,
        (fecha_desde, fecha_hasta, *zona_params),
    )


def ventas_por_dia(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = ()) -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_filtered_facturas(fecha_desde, fecha_hasta, zonas_filtro)
        if df.empty:
            return pd.DataFrame(columns=["fecha", "total", "comprobantes"])
        out = (
            df.assign(fecha=df["fecha"].dt.date)
            .groupby("fecha", as_index=False)
            .agg(total=("total_firmado", "sum"), comprobantes=("id_facturacion", "count"))
            .sort_values("fecha")
        )
        return out

    zona_sql, zona_params = _zona_filter("f", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            CAST(f.fecha AS date) AS fecha,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql}
        GROUP BY CAST(f.fecha AS date)
        ORDER BY fecha;
        """,
        (fecha_desde, fecha_hasta, *zona_params),
    )


def ventas_por_mes(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = ()) -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_filtered_facturas(fecha_desde, fecha_hasta, zonas_filtro)
        if df.empty:
            return pd.DataFrame(columns=["mes", "total", "comprobantes"])
        out = (
            df.assign(mes=df["fecha"].dt.to_period("M").dt.to_timestamp())
            .groupby("mes", as_index=False)
            .agg(total=("total_firmado", "sum"), comprobantes=("id_facturacion", "count"))
            .sort_values("mes")
        )
        return out

    zona_sql, zona_params = _zona_filter("f", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            DATEFROMPARTS(YEAR(f.fecha), MONTH(f.fecha), 1) AS mes,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql}
        GROUP BY DATEFROMPARTS(YEAR(f.fecha), MONTH(f.fecha), 1)
        ORDER BY mes;
        """,
        (fecha_desde, fecha_hasta, *zona_params),
    )


def ventas_por_zona(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = ()) -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_filtered_facturas(fecha_desde, fecha_hasta, zonas_filtro)
        if df.empty:
            return pd.DataFrame(columns=["zona", "total", "comprobantes", "clientes"])
        return (
            df.groupby("zona", as_index=False)
            .agg(
                total=("total_firmado", "sum"),
                comprobantes=("id_facturacion", "count"),
                clientes=("id_cliente", "nunique"),
            )
            .sort_values("total", ascending=False)
        )

    zona_sql, zona_params = _zona_filter("f", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            COALESCE(NULLIF(f.zona, ''), 'Sin zona') AS zona,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes,
            COUNT(DISTINCT f.id_cliente) AS clientes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql}
        GROUP BY COALESCE(NULLIF(f.zona, ''), 'Sin zona')
        ORDER BY total DESC;
        """,
        (fecha_desde, fecha_hasta, *zona_params),
    )


def top_clientes(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = (), limite: int = 15) -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_filtered_facturas(fecha_desde, fecha_hasta, zonas_filtro)
        if df.empty:
            return pd.DataFrame(columns=["cliente", "total", "comprobantes"])
        df["cliente"] = df["cliente"].fillna("")
        empty_client = df["cliente"] == ""
        df.loc[empty_client, "cliente"] = "Cliente " + df.loc[empty_client, "id_cliente"].astype(str)
        return (
            df.groupby("cliente", as_index=False)
            .agg(total=("total_firmado", "sum"), comprobantes=("id_facturacion", "count"))
            .sort_values("total", ascending=False)
            .head(limite)
        )

    zona_sql, zona_params = _zona_filter("f", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT TOP (?)
            COALESCE(NULLIF(f.cliente, ''), CONCAT('Cliente ', f.id_cliente)) AS cliente,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql}
        GROUP BY COALESCE(NULLIF(f.cliente, ''), CONCAT('Cliente ', f.id_cliente))
        ORDER BY total DESC;
        """,
        (limite, fecha_desde, fecha_hasta, *zona_params),
    )


def top_productos(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = (), limite: int = 15) -> pd.DataFrame:
    if data_mode() == "snapshot":
        facturas = _snapshot_filtered_facturas(fecha_desde, fecha_hasta, zonas_filtro)[["id_facturacion", "tipo"]]
        items = _snapshot_factura_items()
        df = items.merge(facturas, on="id_facturacion", how="inner")
        if df.empty:
            return pd.DataFrame(columns=["producto", "cantidad", "total"])
        sign = df["tipo"].map(lambda value: -1 if value == "NC" else 1)
        df["cantidad_firmada"] = df["cantidad"].astype(float) * sign
        df["total_firmado"] = df["total"].astype(float) * sign
        df["producto"] = df["producto"].fillna("")
        empty_product = df["producto"] == ""
        df.loc[empty_product, "producto"] = "Producto " + df.loc[empty_product, "id_producto"].astype(str)
        return (
            df.groupby("producto", as_index=False)
            .agg(cantidad=("cantidad_firmada", "sum"), total=("total_firmado", "sum"))
            .sort_values("total", ascending=False)
            .head(limite)
        )

    zona_sql, zona_params = _zona_filter("f", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT TOP (?)
            COALESCE(NULLIF(fi.descripcion, ''), p.descripcion, CONCAT('Producto ', fi.id_producto)) AS producto,
            SUM(CASE WHEN f.tipo = 'NC' THEN -CAST(fi.cantidad AS decimal(18, 2)) ELSE CAST(fi.cantidad AS decimal(18, 2)) END) AS cantidad,
            SUM(CASE WHEN f.tipo = 'NC' THEN -CAST(fi.total AS decimal(18, 2)) ELSE CAST(fi.total AS decimal(18, 2)) END) AS total
        FROM dbo.cli_factura_item fi
        INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
        LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
        WHERE ISNULL(f.Anulado, 0) = 0
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql}
        GROUP BY COALESCE(NULLIF(fi.descripcion, ''), p.descripcion, CONCAT('Producto ', fi.id_producto))
        ORDER BY total DESC;
        """,
        (limite, fecha_desde, fecha_hasta, *zona_params),
    )


def pedidos_pendientes(zonas_filtro: tuple[str, ...] = ()) -> pd.DataFrame:
    zona_sql, zona_params = _zona_filter("p", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            COUNT(*) AS pedidos,
            SUM(CAST(total AS decimal(18, 2))) AS total
        FROM dbo.pro_pedido p
        WHERE ISNULL(p.Anulado, 0) = 0
          AND p.id_factura IS NULL
          {_commercial_zone_filter("p")}
          {zona_sql};
        """,
        zona_params,
    )


def export_facturas_snapshot(months_back: int = 18) -> pd.DataFrame:
    return read_sql(
        """
        SET NOCOUNT ON;
        SELECT
            id_facturacion,
            CAST(fecha AS datetime) AS fecha,
            tipo,
            tipo_comprobante,
            id_cliente,
            COALESCE(NULLIF(cliente, ''), CONCAT('Cliente ', id_cliente)) AS cliente,
            COALESCE(NULLIF(zona, ''), 'Sin zona') AS zona,
            CAST(total AS decimal(18, 2)) AS total,
            CAST(subtotal AS decimal(18, 2)) AS subtotal
        FROM dbo.cli_factura
        WHERE ISNULL(Anulado, 0) = 0
          AND fecha >= DATEADD(MONTH, -?, CAST(GETDATE() AS date))
          AND COALESCE(NULLIF(zona, ''), 'Sin zona') NOT IN ('PROVEEDORES')
          AND tipo IN ('FC', 'NC', 'ND');
        """,
        (months_back,),
    )


def export_factura_items_snapshot(months_back: int = 18) -> pd.DataFrame:
    return read_sql(
        """
        SET NOCOUNT ON;
        SELECT
            fi.id_facturacion,
            fi.id_producto,
            COALESCE(NULLIF(fi.descripcion, ''), p.descripcion, CONCAT('Producto ', fi.id_producto)) AS producto,
            CAST(fi.cantidad AS decimal(18, 2)) AS cantidad,
            CAST(fi.total AS decimal(18, 2)) AS total
        FROM dbo.cli_factura_item fi
        INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
        LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
        WHERE ISNULL(f.Anulado, 0) = 0
          AND f.fecha >= DATEADD(MONTH, -?, CAST(GETDATE() AS date))
          AND COALESCE(NULLIF(f.zona, ''), 'Sin zona') NOT IN ('PROVEEDORES')
          AND f.tipo IN ('FC', 'NC', 'ND');
        """,
        (months_back,),
    )


def stock_resumen() -> pd.DataFrame:
    return read_sql(
        """
        SET NOCOUNT ON;
        SELECT
            COUNT(DISTINCT s.id_producto) AS productos_con_stock,
            SUM(CAST(s.cantidad AS decimal(18, 2))) AS unidades,
            SUM(CASE WHEN ISNULL(s.cantidad, 0) <= ISNULL(p.stock_minimo, 0) THEN 1 ELSE 0 END) AS bajo_minimo
        FROM dbo.pro_stock s
        LEFT JOIN dbo.pro_producto p ON p.id_producto = s.id_producto;
        """
    )


def mask_config(config: SisCorConfig) -> dict[str, str]:
    return {
        "servidor": config.server,
        "base": config.database,
        "usuario": config.username,
        "driver": config.driver,
        "clave": re.sub(r".", "*", config.password),
    }
