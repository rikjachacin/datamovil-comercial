from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
import math
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
SAMPLE_PEDIDO_ITEMS_PATH = SNAPSHOT_DIR / "sample_pedido_items.csv"
SAMPLE_CLIENTES_PATH = SNAPSHOT_DIR / "sample_clientes.csv"
SAMPLE_CREDITOS_PATH = SNAPSHOT_DIR / "sample_creditos.csv"
SNAPSHOT_KEY_PATH = SNAPSHOT_DIR / "snapshot.key"
DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"
SQL_QUERY_TTL_SECONDS = 30
EXCLUDED_COMMERCIAL_ZONES = ("PROVEEDORES",)
EXCLUDED_PRODUCT_NAMES = ("DESCUENTO PAGO CDO",)
COMMERCIAL_DOCUMENT_TYPES = ("FC", "NC", "ND")
NEGATIVE_COMMERCIAL_DOCUMENT_TYPES = ("NC",)
BALANCE_DOCUMENT_TYPES = ("FC", "ND", "NC", "PC")
NEGATIVE_BALANCE_DOCUMENT_TYPES = ("NC", "PC")
SALES_ZONE_OVERRIDES = (
    {
        "date": "2026-06-03",
        "client": "MENDI ARTE EL 6 SOCIEDAD ANONIMA",
        "source_zone": "LUCIA MORENO",
        "target_zone": "MACA PROTTO",
        "id_facturacion": "281509",
        "invoice_numbers": ("98682", "225914"),
    },
    {
        "date": "2026-07-08",
        "client": "MUNICIPALIDAD DE BERAZATEGUI",
        "client_id": "109186",
        "source_zone": "LUCIA MORENO",
        "target_zone": "DAVID",
        "id_facturacion": "",
        "invoice_numbers": ("229687", "75438", "22882"),
    },
)
SALES_TOTAL_NEUTRALIZED_DOCUMENTS = (
    {
        "date": "2026-07-14",
        "client_id": "117165",
        "source_zone": "LUCIA MORENO",
        "id_facturacion": "288031",
        "invoice_numbers": ("14780", "230258"),
        "document_types": ("NC",),
        "note": "Operacion informada 230258: descuenta deuda, no facturacion de Lucia.",
    },
)


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


def _has_sql_config() -> bool:
    try:
        secrets = st.secrets["siscor"]
        required = ("server", "database", "username", "password")
        return all(str(secrets.get(key, "")).strip() for key in required)
    except Exception:
        return SISCOR_CONFIG_PATH.exists()


def data_mode() -> str:
    env_mode = os.getenv("DATAMOVIL_DATA_MODE")
    if env_mode:
        return env_mode.lower()
    try:
        configured_mode = str(st.secrets.get("data", {}).get("mode", "sql")).lower()
    except StreamlitSecretNotFoundError:
        configured_mode = "sql"

    if configured_mode == "snapshot" and _has_sql_config():
        return "sql"
    return configured_mode


def using_sample_snapshot() -> bool:
    return (
        data_mode() == "snapshot"
        and not (SNAPSHOT_DIR / "facturas.csv").exists()
        and not (SNAPSHOT_DIR / "facturas.csv.enc").exists()
        and SAMPLE_FACTURAS_PATH.exists()
    )


def _to_numeric_amount(values: Any) -> pd.Series:
    raw = pd.Series(values).astype(str).str.strip()
    raw = raw.str.replace("$", "", regex=False).str.replace(" ", "", regex=False)
    has_comma = raw.str.contains(",", regex=False)
    converted = raw.copy()
    converted.loc[has_comma] = converted.loc[has_comma].str.replace(".", "", regex=False).str.replace(
        ",", ".", regex=False
    )
    thousands_dot = converted.str.match(r"^-?\d{1,3}(\.\d{3})+$", na=False)
    converted.loc[thousands_dot] = converted.loc[thousands_dot].str.replace(".", "", regex=False)
    return pd.to_numeric(converted, errors="coerce").fillna(0)


def _raw_zone_expr(alias: str) -> str:
    return f"COALESCE(NULLIF({alias}.zona, ''), 'Sin zona')"


def _sales_zone_expr(alias: str) -> str:
    base_zone = _raw_zone_expr(alias)
    cases = []
    for override in SALES_ZONE_OVERRIDES:
        invoice_numbers = ", ".join(f"'{number}'" for number in override["invoice_numbers"])
        client_condition = f"UPPER(LTRIM(RTRIM(COALESCE({alias}.cliente, '')))) = '{override['client']}'"
        if override.get("client_id"):
            client_condition = (
                f"({client_condition} OR CAST({alias}.id_cliente AS varchar(50)) = '{override['client_id']}')"
            )
        cases.append(
            "WHEN "
            f"CAST({alias}.fecha AS date) = '{override['date']}' "
            f"AND {client_condition} "
            f"AND {base_zone} = '{override['source_zone']}' "
            f"AND (CAST({alias}.id_facturacion AS varchar(50)) = '{override['id_facturacion']}' "
            f"OR CAST({alias}.numero AS varchar(50)) IN ({invoice_numbers})) "
            f"THEN '{override['target_zone']}'"
        )
    return f"CASE {' '.join(cases)} ELSE {base_zone} END"


def _normalize_match_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def _apply_sales_zone_overrides(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "zona" not in df.columns:
        return df

    out = df.copy()
    for override in SALES_ZONE_OVERRIDES:
        mask = pd.Series(True, index=out.index)
        if "fecha" in out.columns:
            mask &= pd.to_datetime(out["fecha"], errors="coerce").dt.date == pd.to_datetime(override["date"]).date()
        if "cliente" in out.columns:
            clients = out["cliente"].map(_normalize_match_text)
            client_mask = clients == override["client"]
            if override.get("client_id") and "id_cliente" in out.columns:
                client_mask |= out["id_cliente"].astype(str).str.strip().eq(str(override["client_id"]))
            mask &= client_mask
        if "zona" in out.columns:
            zones = out["zona"].map(_normalize_match_text)
            mask &= zones == override["source_zone"]

        invoice_mask = pd.Series(False, index=out.index)
        if "id_facturacion" in out.columns:
            invoice_mask |= out["id_facturacion"].astype(str).str.strip().eq(str(override["id_facturacion"]))
        if "numero" in out.columns:
            invoice_numbers = {str(number) for number in override["invoice_numbers"]}
            invoice_mask |= out["numero"].astype(str).str.strip().isin(invoice_numbers)
        mask &= invoice_mask

        out.loc[mask, "zona"] = override["target_zone"]
    return out


def _manual_document_mask(df: pd.DataFrame, rules: tuple[dict[str, object], ...]) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    if df.empty:
        return mask

    for rule in rules:
        rule_mask = pd.Series(True, index=df.index)
        if rule.get("date") and "fecha" in df.columns:
            rule_mask &= pd.to_datetime(df["fecha"], errors="coerce").dt.date == pd.to_datetime(rule["date"]).date()
        if rule.get("client_id") and "id_cliente" in df.columns:
            rule_mask &= df["id_cliente"].astype(str).str.strip().eq(str(rule["client_id"]))
        if rule.get("source_zone") and "zona" in df.columns:
            rule_mask &= df["zona"].map(_normalize_match_text).eq(str(rule["source_zone"]))
        if rule.get("document_types") and "tipo" in df.columns:
            document_types = {str(value).upper() for value in rule["document_types"]}
            rule_mask &= df["tipo"].astype(str).str.upper().isin(document_types)

        invoice_mask = pd.Series(False, index=df.index)
        if rule.get("id_facturacion") and "id_facturacion" in df.columns:
            invoice_mask |= df["id_facturacion"].astype(str).str.strip().eq(str(rule["id_facturacion"]))
        if rule.get("invoice_numbers") and "numero" in df.columns:
            invoice_numbers = {str(number) for number in rule["invoice_numbers"]}
            invoice_mask |= df["numero"].astype(str).str.strip().isin(invoice_numbers)
        rule_mask &= invoice_mask
        mask |= rule_mask
    return mask


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


@st.cache_data(ttl=SQL_QUERY_TTL_SECONDS, show_spinner=False)
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


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot_pedido_items() -> pd.DataFrame:
    df = _read_snapshot_csv("pedido_items.csv", SAMPLE_PEDIDO_ITEMS_PATH)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot_clientes() -> pd.DataFrame:
    try:
        df = _read_snapshot_csv("clientes.csv", SAMPLE_CLIENTES_PATH)
    except SnapshotDataMissing:
        facturas = _snapshot_facturas().copy()
        facturas["zona"] = facturas["zona"].fillna("").replace("", "Sin zona")
        return facturas.loc[:, ["id_cliente", "cliente", "zona"]].drop_duplicates()

    df["zona"] = df["zona"].fillna("").replace("", "Sin zona")
    df["cliente"] = df["cliente"].fillna("")
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot_creditos() -> pd.DataFrame:
    try:
        df = _read_snapshot_csv("creditos.csv", SAMPLE_CREDITOS_PATH)
    except SnapshotDataMissing:
        return pd.DataFrame(columns=_credit_columns())

    df["zona"] = df["zona"].fillna("").replace("", "Sin zona")
    df["cliente"] = df["cliente"].fillna("")
    return df


def _snapshot_filtered_facturas(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    zonas_filtro: tuple[str, ...] = (),
) -> pd.DataFrame:
    df = _snapshot_facturas().copy()
    df["zona"] = df["zona"].fillna("").replace("", "Sin zona")
    df = _apply_sales_zone_overrides(df)
    df = df[~df["zona"].isin(EXCLUDED_COMMERCIAL_ZONES)]
    df = df[df["tipo"].isin(COMMERCIAL_DOCUMENT_TYPES)]
    if "autorizado" in df.columns:
        df = df[df["autorizado"].astype(str).str.lower().isin(("true", "1", "si", "sí"))]

    if fecha_desde:
        df = df[df["fecha"].dt.date >= pd.to_datetime(fecha_desde).date()]
    if fecha_hasta:
        df = df[df["fecha"].dt.date <= pd.to_datetime(fecha_hasta).date()]
    if zonas_filtro:
        df = df[df["zona"].isin(zonas_filtro)]

    sign = _negative_document_mask(df["tipo"]).map(lambda is_negative: -1 if is_negative else 1)
    neutralized = _manual_document_mask(df, SALES_TOTAL_NEUTRALIZED_DOCUMENTS)
    sign.loc[neutralized] = 0
    df["total_firmado"] = _to_numeric_amount(df["total"]) * sign
    df["subtotal_firmado"] = _to_numeric_amount(df["subtotal"]) * sign
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
        WHERE ISNULL(Anulado, 0) = 0
          AND ISNULL(autorizado, 0) = 1;
        """
    )


def _zona_filter(alias: str, zonas: tuple[str, ...], zone_expr: str | None = None) -> tuple[str, tuple[str, ...]]:
    if not zonas:
        return "", ()
    placeholders = ", ".join("?" for _ in zonas)
    expr = zone_expr or _raw_zone_expr(alias)
    return f" AND {expr} IN ({placeholders})", zonas


def _current_client_zone_filter(zones_alias: str, zonas: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    if not zonas:
        return "", ()
    placeholders = ", ".join("?" for _ in zonas)
    return f" AND COALESCE(NULLIF({zones_alias}.descripcion, ''), 'Sin zona') IN ({placeholders})", zonas


def _commercial_zone_filter(alias: str) -> str:
    excluded = ", ".join(f"'{zone}'" for zone in EXCLUDED_COMMERCIAL_ZONES)
    return f" AND COALESCE(NULLIF({alias}.zona, ''), 'Sin zona') NOT IN ({excluded})"


def _commercial_document_filter(alias: str) -> str:
    included = ", ".join(f"'{doc_type}'" for doc_type in COMMERCIAL_DOCUMENT_TYPES)
    return f" AND {alias}.tipo IN ({included})"


def _product_name_expr(item_alias: str = "fi", product_alias: str = "p") -> str:
    return (
        f"COALESCE(NULLIF({item_alias}.descripcion, ''), "
        f"{product_alias}.descripcion, CONCAT('Producto ', {item_alias}.id_producto))"
    )


def _commercial_product_filter(product_expr: str) -> str:
    excluded_conditions = " AND ".join(
        f"UPPER(LTRIM(RTRIM({product_expr}))) NOT LIKE '%{name.replace(' ', '%')}%'"
        for name in EXCLUDED_PRODUCT_NAMES
    )
    return f" AND {excluded_conditions}"


def _filter_commercial_products(df: pd.DataFrame, column: str = "producto") -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df
    patterns = [re.compile(".*".join(re.escape(part) for part in name.upper().split())) for name in EXCLUDED_PRODUCT_NAMES]
    normalized = df[column].fillna("").astype(str).str.upper().str.strip()
    mask = ~normalized.map(lambda value: any(pattern.search(value) for pattern in patterns))
    return df.loc[mask].copy()


def _credit_document_filter(alias: str) -> str:
    return f" AND {alias}.tipo IN ('FC', 'ND')"


def _balance_document_filter(alias: str) -> str:
    included = ", ".join(f"'{doc_type}'" for doc_type in BALANCE_DOCUMENT_TYPES)
    return f" AND {alias}.tipo IN ({included})"


def _authorized_invoice_filter(alias: str) -> str:
    return f" AND ISNULL({alias}.autorizado, 0) = 1"


def _signed_total(alias: str, column: str = "total") -> str:
    negative_types = ", ".join(f"'{doc_type}'" for doc_type in NEGATIVE_COMMERCIAL_DOCUMENT_TYPES)
    neutral_conditions = []
    for rule in SALES_TOTAL_NEUTRALIZED_DOCUMENTS:
        invoice_numbers = ", ".join(f"'{number}'" for number in rule["invoice_numbers"])
        document_types = ", ".join(f"'{doc_type}'" for doc_type in rule["document_types"])
        neutral_conditions.append(
            "("
            f"CAST({alias}.fecha AS date) = '{rule['date']}' "
            f"AND CAST({alias}.id_cliente AS varchar(50)) = '{rule['client_id']}' "
            f"AND COALESCE(NULLIF({alias}.zona, ''), 'Sin zona') = '{rule['source_zone']}' "
            f"AND {alias}.tipo IN ({document_types}) "
            f"AND (CAST({alias}.id_facturacion AS varchar(50)) = '{rule['id_facturacion']}' "
            f"OR CAST({alias}.numero AS varchar(50)) IN ({invoice_numbers}))"
            ")"
        )
    neutral_sql = " OR ".join(neutral_conditions)
    neutral_case = f"WHEN {neutral_sql} THEN CAST(0 AS decimal(18, 2)) " if neutral_sql else ""
    return (
        f"CASE {neutral_case}WHEN {alias}.tipo IN ({negative_types}) "
        f"THEN -CAST({alias}.{column} AS decimal(18, 2)) "
        f"ELSE CAST({alias}.{column} AS decimal(18, 2)) END"
    )


def _signed_item_total(alias: str, column: str = "total") -> str:
    return _signed_total(alias, column)


def _negative_document_mask(values: Any) -> pd.Series:
    return pd.Series(values).astype(str).str.upper().isin(NEGATIVE_COMMERCIAL_DOCUMENT_TYPES)


def _signed_balance(alias: str, column: str = "saldo") -> str:
    negative_types = ", ".join(f"'{doc_type}'" for doc_type in NEGATIVE_BALANCE_DOCUMENT_TYPES)
    return (
        f"CASE WHEN {alias}.tipo IN ({negative_types}) "
        f"THEN -CAST({alias}.{column} AS decimal(18, 2)) "
        f"ELSE CAST({alias}.{column} AS decimal(18, 2)) END"
    )


def _round_to_thousand(value: float) -> float:
    if value <= 0 or math.isnan(value):
        return 0.0
    return round(value / 1000) * 1000.0


def _credit_rule(segment: object) -> tuple[str, int, float, str]:
    rules = {
        "Bueno": ("A", 30, 2.0, "Puede venderse con credito normal amplio"),
        "Normal": ("B", 21, 1.5, "Credito normal controlado"),
        "Lento habitual": ("B", 7, 1.0, "Vender con seguimiento de cobranza"),
        "Riesgoso": ("C", 0, 0.0, "Vender contado o con aprobacion puntual"),
        "Malo": ("C", 0, 0.0, "Vender contado"),
        "Sin historial - limpio": ("B", 7, 0.5, "Limite bajo hasta formar historial"),
        "Sin historial - observar": ("B", 7, 0.3, "Limite muy bajo y seguimiento"),
        "Sin historial - riesgo inicial": ("C", 0, 0.0, "Contado hasta regularizar"),
    }
    return rules.get(str(segment or "").strip(), ("B", 7, 0.3, "Revisar manualmente"))


def _credit_columns() -> list[str]:
    return [
        "cliente",
        "zona",
        "dias_deuda",
        "importe_deuda",
        "saldo_vencido",
        "dias_credito_sugerido",
        "limite_compra_sugerido",
        "categoria_abc",
        "segmento_pago",
        "recomendacion_credito",
    ]


def _credit_profile_from_raw(raw: pd.DataFrame, meses_venta: int = 12) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=_credit_columns())

    out = raw.copy()
    for column in ("monto_facturado", "saldo_actual", "saldo_vencido", "atraso_actual"):
        out[column] = pd.to_numeric(out.get(column, 0), errors="coerce").fillna(0).clip(lower=0)

    rule_values = out["segmento_pago"].fillna("").apply(_credit_rule)
    out["categoria_abc"] = rule_values.apply(lambda item: item[0])
    out["dias_credito_sugerido"] = rule_values.apply(lambda item: item[1])
    out["factor_tope"] = rule_values.apply(lambda item: item[2])
    out["recomendacion_credito"] = rule_values.apply(lambda item: item[3])

    critical_overdue = (out["saldo_vencido"] > 0) & (out["atraso_actual"] >= 45)
    warning_overdue = (out["saldo_vencido"] > 0) & (out["atraso_actual"] >= 15) & ~critical_overdue

    out.loc[critical_overdue, "categoria_abc"] = "C"
    out.loc[critical_overdue, "dias_credito_sugerido"] = 0
    out.loc[critical_overdue, "factor_tope"] = 0.0
    out.loc[critical_overdue, "recomendacion_credito"] = "Contado hasta regularizar deuda vencida"

    out.loc[warning_overdue & (out["categoria_abc"] == "A"), "categoria_abc"] = "B"
    out.loc[warning_overdue, "dias_credito_sugerido"] = out.loc[
        warning_overdue,
        "dias_credito_sugerido",
    ].clip(upper=7)
    out.loc[warning_overdue, "factor_tope"] = out.loc[warning_overdue, "factor_tope"].clip(upper=1.0)
    out.loc[warning_overdue, "recomendacion_credito"] = "Vender con compromiso de pago"

    promedio_mensual = out["monto_facturado"] / meses_venta if meses_venta else 0
    out["limite_compra_sugerido"] = (promedio_mensual * out["factor_tope"]).apply(_round_to_thousand)
    out.loc[out["categoria_abc"] == "C", "limite_compra_sugerido"] = 0
    out.loc[out["categoria_abc"] == "C", "dias_credito_sugerido"] = 0
    out["dias_deuda"] = out["atraso_actual"]
    out["importe_deuda"] = out["saldo_actual"]

    return out.loc[:, _credit_columns()]


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
          AND ISNULL(autorizado, 0) = 1
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

    factura_zone = _sales_zone_expr("f")
    zona_sql, zona_params = _zona_filter("f", zonas_filtro, factura_zone)
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
          {_authorized_invoice_filter("f")}
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

    factura_zone = _sales_zone_expr("f")
    zona_sql, zona_params = _zona_filter("f", zonas_filtro, factura_zone)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            CAST(f.fecha AS date) AS fecha,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          {_authorized_invoice_filter("f")}
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

    factura_zone = _sales_zone_expr("f")
    zona_sql, zona_params = _zona_filter("f", zonas_filtro, factura_zone)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            DATEFROMPARTS(YEAR(f.fecha), MONTH(f.fecha), 1) AS mes,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          {_authorized_invoice_filter("f")}
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

    factura_zone = _sales_zone_expr("f")
    zona_sql, zona_params = _zona_filter("f", zonas_filtro, factura_zone)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            {factura_zone} AS zona,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes,
            COUNT(DISTINCT f.id_cliente) AS clientes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          {_authorized_invoice_filter("f")}
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql}
        GROUP BY {factura_zone}
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
            .loc[lambda data: data["total"].ne(0)]
            .sort_values("total", ascending=False)
            .head(limite)
        )

    factura_zone = _sales_zone_expr("f")
    zona_sql, zona_params = _zona_filter("f", zonas_filtro, factura_zone)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT TOP (?)
            COALESCE(NULLIF(f.cliente, ''), CONCAT('Cliente ', f.id_cliente)) AS cliente,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          {_authorized_invoice_filter("f")}
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql}
        GROUP BY COALESCE(NULLIF(f.cliente, ''), CONCAT('Cliente ', f.id_cliente))
        HAVING SUM({_signed_total("f", "total")}) <> 0
        ORDER BY total DESC;
        """,
        (limite, fecha_desde, fecha_hasta, *zona_params),
    )


def clientes_vendidos(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = ()) -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_filtered_facturas(fecha_desde, fecha_hasta, zonas_filtro)
        if df.empty:
            return pd.DataFrame(columns=["id_cliente", "cliente", "total", "comprobantes"])
        df["cliente"] = df["cliente"].fillna("")
        empty_client = df["cliente"] == ""
        df.loc[empty_client, "cliente"] = "Cliente " + df.loc[empty_client, "id_cliente"].astype(str)
        return (
            df.groupby(["id_cliente", "cliente"], as_index=False)
            .agg(total=("total_firmado", "sum"), comprobantes=("id_facturacion", "count"))
            .sort_values("total", ascending=False)
        )

    factura_zone = _sales_zone_expr("f")
    zona_sql, zona_params = _zona_filter("f", zonas_filtro, factura_zone)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            CAST(f.id_cliente AS varchar(50)) AS id_cliente,
            COALESCE(NULLIF(f.cliente, ''), CONCAT('Cliente ', f.id_cliente)) AS cliente,
            SUM({_signed_total("f", "total")}) AS total,
            COUNT(*) AS comprobantes
        FROM dbo.cli_factura f
        WHERE ISNULL(f.Anulado, 0) = 0
          {_authorized_invoice_filter("f")}
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {zona_sql}
        GROUP BY CAST(f.id_cliente AS varchar(50)), COALESCE(NULLIF(f.cliente, ''), CONCAT('Cliente ', f.id_cliente))
        ORDER BY total DESC;
        """,
        (fecha_desde, fecha_hasta, *zona_params),
    )


def top_productos(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = (), limite: int = 15) -> pd.DataFrame:
    if data_mode() == "snapshot":
        facturas = _snapshot_filtered_facturas(fecha_desde, fecha_hasta, zonas_filtro)[["id_facturacion", "tipo"]]
        items = _snapshot_factura_items()
        df = items.merge(facturas, on="id_facturacion", how="inner")
        if df.empty:
            return pd.DataFrame(columns=["producto", "cantidad", "total"])
        sign = _negative_document_mask(df["tipo"]).map(lambda is_negative: -1 if is_negative else 1)
        df["cantidad_firmada"] = _to_numeric_amount(df["cantidad"]) * sign
        df["total_firmado"] = _to_numeric_amount(df["total"]) * sign
        df["producto"] = df["producto"].fillna("")
        empty_product = df["producto"] == ""
        df.loc[empty_product, "producto"] = "Producto " + df.loc[empty_product, "id_producto"].astype(str)
        df = _filter_commercial_products(df)
        return (
            df.groupby("producto", as_index=False)
            .agg(cantidad=("cantidad_firmada", "sum"), total=("total_firmado", "sum"))
            .sort_values("total", ascending=False)
            .head(limite)
        )

    factura_zone = _sales_zone_expr("f")
    zona_sql, zona_params = _zona_filter("f", zonas_filtro, factura_zone)
    product_expr = _product_name_expr("fi", "p")
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT TOP (?)
            {product_expr} AS producto,
            SUM({_signed_item_total("f", "cantidad").replace("f.cantidad", "fi.cantidad")}) AS cantidad,
            SUM({_signed_item_total("f", "total").replace("f.total", "fi.total")}) AS total
        FROM dbo.cli_factura_item fi
        INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
        LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
        WHERE ISNULL(f.Anulado, 0) = 0
          {_authorized_invoice_filter("f")}
          AND CAST(f.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("f")}
          {_commercial_document_filter("f")}
          {_commercial_product_filter(product_expr)}
          {zona_sql}
        GROUP BY {product_expr}
        ORDER BY total DESC;
        """,
        (limite, fecha_desde, fecha_hasta, *zona_params),
    )


def ventas_por_marca(fecha_desde: str, fecha_hasta: str, zonas_filtro: tuple[str, ...] = ()) -> pd.DataFrame:
    columns = ["zona", "marca", "total"]
    if data_mode() == "snapshot":
        df = _snapshot_pedido_items().copy()
        if df.empty or "marca" not in df.columns:
            return pd.DataFrame(columns=columns)
        df["zona"] = df["zona"].fillna("").replace("", "Sin zona")
        df = df[~df["zona"].isin(EXCLUDED_COMMERCIAL_ZONES)]
        df = df[df["tipo"].astype(str).str.upper().isin(("P", "PD"))]
        df = df[df["fecha"].dt.date >= pd.to_datetime(fecha_desde).date()]
        df = df[df["fecha"].dt.date <= pd.to_datetime(fecha_hasta).date()]
        if zonas_filtro:
            df = df[df["zona"].isin(zonas_filtro)]
        sign = df["tipo"].astype(str).str.upper().map(lambda value: -1 if value == "PD" else 1)
        df["total_firmado"] = _to_numeric_amount(df["total"]) * sign
        df["marca"] = df["marca"].fillna("").astype(str).str.strip()
        df = df[df["marca"].ne("")]
        if df.empty:
            return pd.DataFrame(columns=columns)
        return (
            df.groupby(["zona", "marca"], as_index=False)
            .agg(total=("total_firmado", "sum"))
            .sort_values("total", ascending=False)
        )

    zona_sql, zona_params = _zona_filter("p", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            COALESCE(NULLIF(p.zona, ''), 'Sin zona') AS zona,
            COALESCE(NULLIF(pi.marca, ''), 'Sin marca') AS marca,
            SUM(CASE WHEN p.tipo = 'PD' THEN -CAST(pi.total AS decimal(18, 2)) ELSE CAST(pi.total AS decimal(18, 2)) END) AS total
        FROM dbo.pro_pedido p
        INNER JOIN dbo.pro_pedido_item pi ON pi.id_pedido = p.id_pedido
        WHERE ISNULL(p.Anulado, 0) = 0
          AND CAST(p.fecha AS date) BETWEEN ? AND ?
          {_commercial_zone_filter("p")}
          AND p.tipo IN ('P', 'PD')
          {zona_sql}
        GROUP BY COALESCE(NULLIF(p.zona, ''), 'Sin zona'), COALESCE(NULLIF(pi.marca, ''), 'Sin marca')
        ORDER BY total DESC;
        """,
        (fecha_desde, fecha_hasta, *zona_params),
    )


def clientes_a_recuperar(
    mes_actual_desde: str,
    fecha_hasta: str,
    mes_anterior_desde: str,
    mes_anterior_hasta: str,
    zonas_filtro: tuple[str, ...] = (),
    limite: int = 20,
) -> pd.DataFrame:
    if data_mode() == "snapshot":
        actual = _snapshot_filtered_facturas(mes_actual_desde, fecha_hasta, zonas_filtro)
        anterior = _snapshot_filtered_facturas(mes_anterior_desde, mes_anterior_hasta, zonas_filtro)
        return _clientes_a_recuperar_from_frames(actual, anterior, limite)

    zona_sql, zona_params = _current_client_zone_filter("z", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        WITH cartera AS (
            SELECT DISTINCT
                c.id_cliente,
                COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente)) AS cliente,
                COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') AS zona
            FROM dbo.cli_cliente c
            INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
            LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
            WHERE ISNULL(c.activo, 0) = 1
              AND ISNULL(cs.activo, 0) = 1
              {zona_sql}
        ),
        actual AS (
            SELECT
                f.id_cliente,
                c.cliente,
                c.zona,
                SUM({_signed_total("f", "total")}) AS venta_mes
            FROM dbo.cli_factura f
            INNER JOIN cartera c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
            GROUP BY f.id_cliente, c.cliente, c.zona
        ),
        anterior AS (
            SELECT
                f.id_cliente,
                c.cliente,
                c.zona,
                SUM({_signed_total("f", "total")}) AS venta_mes_anterior
            FROM dbo.cli_factura f
            INNER JOIN cartera c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
            GROUP BY f.id_cliente, c.cliente, c.zona
        )
        SELECT TOP (?)
            COALESCE(a.cliente, p.cliente) AS cliente,
            COALESCE(a.zona, p.zona) AS zona,
            ISNULL(a.venta_mes, 0) AS venta_mes,
            ISNULL(p.venta_mes_anterior, 0) AS venta_mes_anterior,
            ISNULL(a.venta_mes, 0) - ISNULL(p.venta_mes_anterior, 0) AS variacion,
            CASE
                WHEN ISNULL(a.venta_mes, 0) = 0 AND ISNULL(p.venta_mes_anterior, 0) > 0 THEN 'Recuperar visita'
                WHEN ISNULL(a.venta_mes, 0) < ISNULL(p.venta_mes_anterior, 0) * 0.6 THEN 'Reactivar compra'
                ELSE 'Dar seguimiento'
            END AS accion
        FROM actual a
        FULL OUTER JOIN anterior p
            ON p.id_cliente = a.id_cliente
           AND p.zona = a.zona
        WHERE ISNULL(p.venta_mes_anterior, 0) > 0
          AND ISNULL(a.venta_mes, 0) < ISNULL(p.venta_mes_anterior, 0) * 0.8
        ORDER BY variacion ASC;
        """,
        (
            *zona_params,
            mes_actual_desde,
            fecha_hasta,
            mes_anterior_desde,
            mes_anterior_hasta,
            limite,
        ),
    )


def _clientes_a_recuperar_from_frames(actual: pd.DataFrame, anterior: pd.DataFrame, limite: int) -> pd.DataFrame:
    columns = ["cliente", "zona", "venta_mes", "venta_mes_anterior", "variacion", "accion"]
    if anterior.empty:
        return pd.DataFrame(columns=columns)

    def grouped(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["id_cliente", "cliente", "zona", value_name])
        temp = df.copy()
        temp["cliente"] = temp["cliente"].fillna("")
        empty_client = temp["cliente"] == ""
        temp.loc[empty_client, "cliente"] = "Cliente " + temp.loc[empty_client, "id_cliente"].astype(str)
        return (
            temp.groupby(["id_cliente", "cliente", "zona"], as_index=False)
            .agg(**{value_name: ("total_firmado", "sum")})
        )

    current = grouped(actual, "venta_mes")
    previous = grouped(anterior, "venta_mes_anterior")
    out = previous.merge(current, on=["id_cliente", "cliente", "zona"], how="left")
    out["venta_mes"] = out["venta_mes"].fillna(0)
    out["variacion"] = out["venta_mes"] - out["venta_mes_anterior"]
    out = out[(out["venta_mes_anterior"] > 0) & (out["venta_mes"] < out["venta_mes_anterior"] * 0.8)]
    out["accion"] = out.apply(
        lambda row: "Recuperar visita"
        if row["venta_mes"] == 0
        else "Reactivar compra"
        if row["venta_mes"] < row["venta_mes_anterior"] * 0.6
        else "Dar seguimiento",
        axis=1,
    )
    return out.sort_values("variacion").head(limite).loc[:, columns]


def productos_a_impulsar(
    mes_actual_desde: str,
    fecha_hasta: str,
    mes_anterior_desde: str,
    mes_anterior_hasta: str,
    zonas_filtro: tuple[str, ...] = (),
    limite: int = 20,
) -> pd.DataFrame:
    if data_mode() == "snapshot":
        actual_facturas = _snapshot_filtered_facturas(mes_actual_desde, fecha_hasta, zonas_filtro)[["id_facturacion", "tipo"]]
        anterior_facturas = _snapshot_filtered_facturas(mes_anterior_desde, mes_anterior_hasta, zonas_filtro)[
            ["id_facturacion", "tipo"]
        ]
        items = _snapshot_factura_items()
        actual = items.merge(actual_facturas, on="id_facturacion", how="inner")
        anterior = items.merge(anterior_facturas, on="id_facturacion", how="inner")
        return _productos_a_impulsar_from_frames(actual, anterior, limite)

    factura_zone = _sales_zone_expr("f")
    zona_sql, zona_params = _zona_filter("f", zonas_filtro, factura_zone)
    product_expr = _product_name_expr("fi", "p")
    return read_sql(
        f"""
        SET NOCOUNT ON;
        WITH actual AS (
            SELECT
                fi.id_producto,
                {product_expr} AS producto,
                SUM({_signed_item_total("f", "cantidad").replace("f.cantidad", "fi.cantidad")}) AS cantidad_mes,
                SUM({_signed_item_total("f", "total").replace("f.total", "fi.total")}) AS venta_mes
            FROM dbo.cli_factura_item fi
            INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
            LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
              {_commercial_product_filter(product_expr)}
              {zona_sql}
            GROUP BY fi.id_producto, {product_expr}
        ),
        anterior AS (
            SELECT
                fi.id_producto,
                {product_expr} AS producto,
                SUM({_signed_item_total("f", "cantidad").replace("f.cantidad", "fi.cantidad")}) AS cantidad_mes_anterior,
                SUM({_signed_item_total("f", "total").replace("f.total", "fi.total")}) AS venta_mes_anterior
            FROM dbo.cli_factura_item fi
            INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
            LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
              {_commercial_product_filter(product_expr)}
              {zona_sql}
            GROUP BY fi.id_producto, {product_expr}
        )
        SELECT TOP (?)
            COALESCE(a.producto, p.producto) AS producto,
            ISNULL(a.cantidad_mes, 0) AS cantidad_mes,
            ISNULL(p.cantidad_mes_anterior, 0) AS cantidad_mes_anterior,
            ISNULL(a.venta_mes, 0) AS venta_mes,
            ISNULL(p.venta_mes_anterior, 0) AS venta_mes_anterior,
            ISNULL(a.venta_mes, 0) - ISNULL(p.venta_mes_anterior, 0) AS variacion,
            CASE
                WHEN ISNULL(a.venta_mes, 0) = 0 AND ISNULL(p.venta_mes_anterior, 0) > 0 THEN 'Reponer en la conversacion'
                WHEN ISNULL(a.venta_mes, 0) < ISNULL(p.venta_mes_anterior, 0) * 0.6 THEN 'Impulsar oferta'
                ELSE 'Monitorear'
            END AS accion
        FROM actual a
        FULL OUTER JOIN anterior p ON p.id_producto = a.id_producto
        WHERE ISNULL(p.venta_mes_anterior, 0) > 0
          AND ISNULL(a.venta_mes, 0) < ISNULL(p.venta_mes_anterior, 0) * 0.8
        ORDER BY variacion ASC;
        """,
        (
            mes_actual_desde,
            fecha_hasta,
            *zona_params,
            mes_anterior_desde,
            mes_anterior_hasta,
            *zona_params,
            limite,
        ),
    )


def _productos_a_impulsar_from_frames(actual: pd.DataFrame, anterior: pd.DataFrame, limite: int) -> pd.DataFrame:
    columns = [
        "producto",
        "cantidad_mes",
        "cantidad_mes_anterior",
        "venta_mes",
        "venta_mes_anterior",
        "variacion",
        "accion",
    ]
    if anterior.empty:
        return pd.DataFrame(columns=columns)

    def signed_items(df: pd.DataFrame, qty_name: str, total_name: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["id_producto", "producto", qty_name, total_name])
        temp = df.copy()
        sign = _negative_document_mask(temp["tipo"]).map(lambda is_negative: -1 if is_negative else 1)
        temp[qty_name] = _to_numeric_amount(temp["cantidad"]) * sign
        temp[total_name] = _to_numeric_amount(temp["total"]) * sign
        temp["producto"] = temp["producto"].fillna("")
        empty_product = temp["producto"] == ""
        temp.loc[empty_product, "producto"] = "Producto " + temp.loc[empty_product, "id_producto"].astype(str)
        temp = _filter_commercial_products(temp)
        return (
            temp.groupby(["id_producto", "producto"], as_index=False)
            .agg(**{qty_name: (qty_name, "sum"), total_name: (total_name, "sum")})
        )

    current = signed_items(actual, "cantidad_mes", "venta_mes")
    previous = signed_items(anterior, "cantidad_mes_anterior", "venta_mes_anterior")
    out = previous.merge(current, on=["id_producto", "producto"], how="left")
    out["cantidad_mes"] = out["cantidad_mes"].fillna(0)
    out["venta_mes"] = out["venta_mes"].fillna(0)
    out["variacion"] = out["venta_mes"] - out["venta_mes_anterior"]
    out = out[(out["venta_mes_anterior"] > 0) & (out["venta_mes"] < out["venta_mes_anterior"] * 0.8)]
    out["accion"] = out.apply(
        lambda row: "Reponer en la conversacion"
        if row["venta_mes"] == 0
        else "Impulsar oferta"
        if row["venta_mes"] < row["venta_mes_anterior"] * 0.6
        else "Monitorear",
        axis=1,
    )
    return out.sort_values("variacion").head(limite).loc[:, columns]


def clientes_busqueda(zonas_filtro: tuple[str, ...] = ()) -> pd.DataFrame:
    if data_mode() == "snapshot":
        df = _snapshot_clientes()
        df = df[~df["zona"].isin(EXCLUDED_COMMERCIAL_ZONES)]
        if zonas_filtro:
            df = df[df["zona"].isin(zonas_filtro)]
        if df.empty:
            return pd.DataFrame(columns=["cliente"])
        return pd.DataFrame({"cliente": sorted(df["cliente"].dropna().astype(str).unique())})

    zona_sql, zona_params = _current_client_zone_filter("z", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT DISTINCT
            COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente)) AS cliente
        FROM dbo.cli_cliente c
        INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
        LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
        WHERE ISNULL(c.activo, 0) = 1
          AND ISNULL(cs.activo, 0) = 1
          {zona_sql}
        ORDER BY cliente;
        """,
        zona_params,
    )


def cliente_credito(
    cliente: str,
    zonas_filtro: tuple[str, ...] = (),
    meses_venta: int = 12,
    meses_pago: int = 24,
) -> pd.DataFrame:
    columns = [column for column in _credit_columns() if column not in ("cliente", "zona")]
    if data_mode() == "snapshot":
        creditos = _snapshot_creditos()
        creditos = creditos[creditos["cliente"].astype(str) == cliente]
        if zonas_filtro:
            creditos = creditos[creditos["zona"].isin(zonas_filtro)]
        if creditos.empty:
            return pd.DataFrame(
                [
                    {
                        "dias_deuda": 0,
                        "importe_deuda": 0,
                        "saldo_vencido": 0,
                        "dias_credito_sugerido": 0,
                        "limite_compra_sugerido": 0,
                        "categoria_abc": "Sin datos",
                        "segmento_pago": "Cliente no encontrado en snapshot de credito",
                        "recomendacion_credito": "Actualizar datos de credito desde SisCor.",
                    }
                ],
                columns=columns,
            )
        return creditos.loc[:, columns].head(1)

    zona_sql, zona_params = _current_client_zone_filter("z", zonas_filtro)
    cliente_ids_df = read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT DISTINCT
            c.id_cliente
        FROM dbo.cli_cliente c
        INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
        LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
        WHERE ISNULL(c.activo, 0) = 1
          AND ISNULL(cs.activo, 0) = 1
          AND COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente)) = ?
          {zona_sql};
        """,
        (cliente, *zona_params),
    )
    if cliente_ids_df.empty:
        return pd.DataFrame(
            [
                {
                    "dias_deuda": 0,
                    "importe_deuda": 0,
                    "saldo_vencido": 0,
                    "dias_credito_sugerido": 0,
                    "limite_compra_sugerido": 0,
                    "categoria_abc": "Sin datos",
                    "segmento_pago": "Cliente no encontrado",
                    "recomendacion_credito": "Revisar asignacion del cliente.",
                }
            ],
            columns=columns,
        )

    cliente_ids = tuple(int(value) for value in cliente_ids_df["id_cliente"].dropna().unique())
    cliente_placeholders = ", ".join("?" for _ in cliente_ids)
    signed_balance = _signed_balance("f", "saldo")

    profile = read_sql(
        f"""
        SET NOCOUNT ON;
        WITH ventas AS (
            SELECT
                ISNULL(SUM({_signed_total("f", "total")}), 0) AS monto_facturado
            FROM dbo.cli_factura f
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.id_cliente IN ({cliente_placeholders})
              AND f.fecha >= DATEADD(month, -?, GETDATE())
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
        ),
        pagos AS (
            SELECT
                COUNT(*) AS facturas_cobradas,
                AVG(CAST(DATEDIFF(day, f.fecha, f.fecha_liquidacion) AS decimal(18, 2))) AS dias_promedio_pago,
                MAX(DATEDIFF(day, f.fecha, f.fecha_liquidacion)) AS peor_pago,
                SUM(CASE WHEN DATEDIFF(day, f.fecha, f.fecha_liquidacion) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) AS pagos_31_60,
                SUM(CASE WHEN DATEDIFF(day, f.fecha, f.fecha_liquidacion) > 60 THEN 1 ELSE 0 END) AS pagos_mas_60
            FROM dbo.cli_factura f
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND ISNULL(f.cobrado, 0) = 1
              AND f.fecha_liquidacion IS NOT NULL
              AND DATEDIFF(day, f.fecha, f.fecha_liquidacion) >= 0
              AND f.id_cliente IN ({cliente_placeholders})
              AND f.fecha >= DATEADD(month, -?, GETDATE())
              {_commercial_zone_filter("f")}
              {_credit_document_filter("f")}
        ),
        deuda AS (
            SELECT
                ISNULL(SUM(CASE WHEN f.saldo <> 0 THEN {signed_balance} ELSE 0 END), 0) AS saldo_actual,
                ISNULL(SUM(CASE WHEN f.saldo <> 0
                    AND CAST(COALESCE(f.fecha_vencimiento, f.fecha) AS date) < CAST(GETDATE() AS date)
                    THEN {signed_balance} ELSE 0 END), 0) AS saldo_vencido,
                ISNULL(MAX(CASE WHEN f.saldo <> 0
                    THEN DATEDIFF(day, COALESCE(f.fecha_vencimiento, f.fecha), GETDATE())
                    ELSE 0 END), 0) AS atraso_actual
            FROM dbo.cli_factura f
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.id_cliente IN ({cliente_placeholders})
              AND f.saldo <> 0
              {_commercial_zone_filter("f")}
              {_balance_document_filter("f")}
        )
        SELECT
            v.monto_facturado,
            COALESCE(p.facturas_cobradas, 0) AS facturas_cobradas,
            COALESCE(p.dias_promedio_pago, 0) AS dias_promedio_pago,
            COALESCE(p.peor_pago, 0) AS peor_pago,
            COALESCE(p.pagos_31_60, 0) AS pagos_31_60,
            COALESCE(p.pagos_mas_60, 0) AS pagos_mas_60,
            d.saldo_actual,
            d.saldo_vencido,
            d.atraso_actual,
            CASE
                WHEN COALESCE(p.facturas_cobradas, 0) < 3 AND d.saldo_actual <= 0 THEN 'Sin historial - limpio'
                WHEN COALESCE(p.facturas_cobradas, 0) < 3 AND d.saldo_vencido > 0 THEN 'Sin historial - riesgo inicial'
                WHEN COALESCE(p.facturas_cobradas, 0) < 3 AND d.saldo_actual > 0 THEN 'Sin historial - observar'
                WHEN p.dias_promedio_pago <= 7 AND 100.0 * (p.pagos_31_60 + p.pagos_mas_60) / NULLIF(p.facturas_cobradas, 0) <= 10 THEN 'Bueno'
                WHEN p.dias_promedio_pago <= 20
                    AND 100.0 * (p.pagos_31_60 + p.pagos_mas_60) / NULLIF(p.facturas_cobradas, 0) <= 20
                    AND 100.0 * p.pagos_mas_60 / NULLIF(p.facturas_cobradas, 0) <= 10 THEN 'Normal'
                WHEN 100.0 * (p.pagos_31_60 + p.pagos_mas_60) / NULLIF(p.facturas_cobradas, 0) >= 70
                    AND d.saldo_vencido > 0 THEN 'Riesgoso'
                WHEN p.dias_promedio_pago <= 45 OR 100.0 * (p.pagos_31_60 + p.pagos_mas_60) / NULLIF(p.facturas_cobradas, 0) <= 45 THEN 'Lento habitual'
                WHEN p.dias_promedio_pago <= 70 OR 100.0 * p.pagos_mas_60 / NULLIF(p.facturas_cobradas, 0) <= 35 THEN 'Riesgoso'
                ELSE 'Malo'
            END AS segmento_pago
        FROM ventas v
        CROSS JOIN pagos p
        CROSS JOIN deuda d;
        """,
        (
            *cliente_ids,
            meses_venta,
            *cliente_ids,
            meses_pago,
            *cliente_ids,
        ),
    )
    if profile.empty:
        return pd.DataFrame(columns=columns)

    profile["cliente"] = cliente
    profile["zona"] = zonas_filtro[0] if zonas_filtro else "Sin zona"
    return _credit_profile_from_raw(profile, meses_venta).loc[:, columns]


def cartera_vencida(
    zonas_filtro: tuple[str, ...] = (),
    dias_minimos: int = 30,
) -> pd.DataFrame:
    """Return current overdue balances without modifying SisCor data."""
    columns = [
        "cliente",
        "zona",
        "importe_vencido",
        "dias_mora",
        "documento_mas_antiguo",
        "vencimiento_mas_antiguo",
        "ultima_compra",
    ]

    if data_mode() == "snapshot":
        creditos = _snapshot_creditos().copy()
        if creditos.empty:
            return pd.DataFrame(columns=columns)

        creditos["dias_deuda"] = pd.to_numeric(creditos["dias_deuda"], errors="coerce").fillna(0)
        creditos["saldo_vencido"] = pd.to_numeric(
            creditos["saldo_vencido"], errors="coerce"
        ).fillna(0)
        creditos = creditos[
            (creditos["dias_deuda"] > dias_minimos) & (creditos["saldo_vencido"] > 0)
        ].copy()
        if zonas_filtro:
            creditos = creditos[creditos["zona"].isin(zonas_filtro)]
        if creditos.empty:
            return pd.DataFrame(columns=columns)

        facturas = _snapshot_filtered_facturas(zonas_filtro=zonas_filtro)
        ultimas = (
            facturas.groupby("cliente", as_index=False)["fecha"].max().rename(columns={"fecha": "ultima_compra"})
            if not facturas.empty
            else pd.DataFrame(columns=["cliente", "ultima_compra"])
        )
        result = creditos.loc[:, ["cliente", "zona", "saldo_vencido", "dias_deuda"]].rename(
            columns={"saldo_vencido": "importe_vencido", "dias_deuda": "dias_mora"}
        )
        result = result.merge(ultimas, on="cliente", how="left")
        result["documento_mas_antiguo"] = "Sin detalle en snapshot"
        result["vencimiento_mas_antiguo"] = pd.NaT
        return result.loc[:, columns].sort_values(
            ["dias_mora", "importe_vencido"], ascending=[False, False]
        )

    dias_minimos = max(int(dias_minimos), 0)
    signed_balance = _signed_balance("f", "saldo")
    zona_sql, zona_params = _current_client_zone_filter("z", zonas_filtro)
    return read_sql(
        f"""
        SET NOCOUNT ON;
        WITH clientes AS (
            SELECT
                c.id_cliente,
                MAX(COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente))) AS cliente,
                MAX(COALESCE(NULLIF(z.descripcion, ''), 'Sin zona')) AS zona
            FROM dbo.cli_cliente c
            INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
            LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
            WHERE ISNULL(c.activo, 0) = 1
              AND ISNULL(cs.activo, 0) = 1
              AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') NOT IN ('PROVEEDORES')
              {zona_sql}
            GROUP BY c.id_cliente
        ),
        deuda_documentos AS (
            SELECT
                f.id_cliente,
                {signed_balance} AS saldo_firmado,
                CAST(COALESCE(f.fecha_vencimiento, f.fecha) AS date) AS fecha_vencimiento,
                DATEDIFF(day, COALESCE(f.fecha_vencimiento, f.fecha), GETDATE()) AS dias_mora,
                CONCAT(f.tipo, ' ', CAST(f.numero AS varchar(50))) AS documento,
                ROW_NUMBER() OVER (
                    PARTITION BY f.id_cliente
                    ORDER BY COALESCE(f.fecha_vencimiento, f.fecha), f.id_facturacion
                ) AS orden_antiguedad
            FROM dbo.cli_factura f
            INNER JOIN clientes c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.saldo <> 0
              AND DATEDIFF(day, COALESCE(f.fecha_vencimiento, f.fecha), GETDATE()) > ?
              {_commercial_zone_filter("f")}
              {_balance_document_filter("f")}
        ),
        deuda AS (
            SELECT
                id_cliente,
                SUM(saldo_firmado) AS importe_vencido,
                MAX(dias_mora) AS dias_mora,
                MAX(CASE WHEN orden_antiguedad = 1 THEN documento END) AS documento_mas_antiguo,
                MIN(fecha_vencimiento) AS vencimiento_mas_antiguo
            FROM deuda_documentos
            GROUP BY id_cliente
            HAVING SUM(saldo_firmado) > 0
        ),
        compras AS (
            SELECT
                f.id_cliente,
                MAX(CAST(f.fecha AS date)) AS ultima_compra
            FROM dbo.cli_factura f
            INNER JOIN clientes c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              {_commercial_zone_filter("f")}
              {_credit_document_filter("f")}
            GROUP BY f.id_cliente
        )
        SELECT
            c.cliente,
            c.zona,
            d.importe_vencido,
            d.dias_mora,
            d.documento_mas_antiguo,
            d.vencimiento_mas_antiguo,
            p.ultima_compra
        FROM deuda d
        INNER JOIN clientes c ON c.id_cliente = d.id_cliente
        LEFT JOIN compras p ON p.id_cliente = d.id_cliente
        ORDER BY d.dias_mora DESC, d.importe_vencido DESC;
        """,
        (*zona_params, dias_minimos),
    ).loc[:, columns]


def estrategia_cliente(
    cliente: str,
    mes_actual_desde: str,
    fecha_hasta: str,
    mes_anterior_desde: str,
    mes_anterior_hasta: str,
    zonas_filtro: tuple[str, ...] = (),
    limite_productos: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if data_mode() == "snapshot":
        clientes = _snapshot_clientes()
        clientes = clientes[clientes["cliente"].astype(str) == cliente]
        if zonas_filtro:
            clientes = clientes[clientes["zona"].isin(zonas_filtro)]
        if clientes.empty:
            resumen = pd.DataFrame(
                {
                    "venta_mes": [0],
                    "venta_mes_anterior": [0],
                    "comprobantes_mes": [0],
                    "ultima_compra": [None],
                }
            )
            productos = pd.DataFrame(columns=["producto", "cantidad", "total"])
            caidos = pd.DataFrame(columns=["producto", "venta_mes", "venta_mes_anterior", "variacion"])
            return resumen, productos, caidos
        actual = _snapshot_filtered_facturas(mes_actual_desde, fecha_hasta, zonas_filtro)
        anterior = _snapshot_filtered_facturas(mes_anterior_desde, mes_anterior_hasta, zonas_filtro)
        return _estrategia_cliente_from_frames(cliente, actual, anterior, limite_productos)

    zona_sql, zona_params = _current_client_zone_filter("z", zonas_filtro)
    cliente_ids_df = read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT DISTINCT
            c.id_cliente
        FROM dbo.cli_cliente c
        INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
        LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
        WHERE ISNULL(c.activo, 0) = 1
          AND ISNULL(cs.activo, 0) = 1
          AND COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente)) = ?
          {zona_sql};
        """,
        (cliente, *zona_params),
    )
    if cliente_ids_df.empty:
        resumen = pd.DataFrame(
            {
                "venta_mes": [0],
                "venta_mes_anterior": [0],
                "comprobantes_mes": [0],
                "ultima_compra": [None],
            }
        )
        productos = pd.DataFrame(columns=["producto", "cantidad", "total"])
        caidos = pd.DataFrame(columns=["producto", "venta_mes", "venta_mes_anterior", "variacion"])
        return resumen, productos, caidos

    cliente_ids = tuple(int(value) for value in cliente_ids_df["id_cliente"].dropna().unique())
    cliente_placeholders = ", ".join("?" for _ in cliente_ids)

    resumen = read_sql(
        f"""
        SET NOCOUNT ON;
        WITH base AS (
            SELECT
                CASE
                    WHEN CAST(f.fecha AS date) BETWEEN ? AND ? THEN 'actual'
                    WHEN CAST(f.fecha AS date) BETWEEN ? AND ? THEN 'anterior'
                    ELSE 'historico'
                END AS periodo,
                {_signed_total("f", "total")} AS total,
                f.id_facturacion,
                CAST(f.fecha AS date) AS fecha
            FROM dbo.cli_factura f
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.id_cliente IN ({cliente_placeholders})
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
        )
        SELECT
            ISNULL(SUM(CASE WHEN periodo = 'actual' THEN total ELSE 0 END), 0) AS venta_mes,
            ISNULL(SUM(CASE WHEN periodo = 'anterior' THEN total ELSE 0 END), 0) AS venta_mes_anterior,
            COUNT(CASE WHEN periodo = 'actual' THEN id_facturacion END) AS comprobantes_mes,
            MAX(fecha) AS ultima_compra
        FROM base;
        """,
        (
            mes_actual_desde,
            fecha_hasta,
            mes_anterior_desde,
            mes_anterior_hasta,
            *cliente_ids,
            mes_anterior_desde,
            fecha_hasta,
        ),
    )
    product_expr = _product_name_expr("fi", "p")
    productos = read_sql(
        f"""
        SET NOCOUNT ON;
        WITH productos AS (
            SELECT
                {product_expr} AS producto,
                SUM(CASE WHEN CAST(f.fecha AS date) BETWEEN ? AND ?
                    THEN {_signed_item_total("f", "cantidad").replace("f.cantidad", "fi.cantidad")}
                    ELSE 0 END) AS cantidad,
                SUM(CASE WHEN CAST(f.fecha AS date) BETWEEN ? AND ?
                    THEN {_signed_item_total("f", "total").replace("f.total", "fi.total")}
                    ELSE 0 END) AS total,
                SUM(CASE WHEN CAST(f.fecha AS date) BETWEEN ? AND ?
                    THEN {_signed_item_total("f", "cantidad").replace("f.cantidad", "fi.cantidad")}
                    ELSE 0 END) AS cantidad_anterior,
                SUM(CASE WHEN CAST(f.fecha AS date) BETWEEN ? AND ?
                    THEN {_signed_item_total("f", "total").replace("f.total", "fi.total")}
                    ELSE 0 END) AS total_anterior
                ,
                SUM(CASE WHEN CAST(f.fecha AS date) BETWEEN ? AND ?
                    THEN {_signed_item_total("f", "cantidad").replace("f.cantidad", "fi.cantidad")}
                    ELSE 0 END) AS cantidad_historica,
                SUM(CASE WHEN CAST(f.fecha AS date) BETWEEN ? AND ?
                    THEN {_signed_item_total("f", "total").replace("f.total", "fi.total")}
                    ELSE 0 END) AS total_historico
            FROM dbo.cli_factura_item fi
            INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
            LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.id_cliente IN ({cliente_placeholders})
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
              {_commercial_product_filter(product_expr)}
            GROUP BY {product_expr}
        )
        SELECT TOP (?)
            producto,
            CASE
                WHEN total <> 0 THEN cantidad
                WHEN total_anterior <> 0 THEN cantidad_anterior
                ELSE cantidad_historica
            END AS cantidad,
            CASE
                WHEN total <> 0 THEN total
                WHEN total_anterior <> 0 THEN total_anterior
                ELSE total_historico
            END AS total
        FROM productos
        ORDER BY CASE WHEN total <> 0 THEN total WHEN total_anterior <> 0 THEN total_anterior ELSE total_historico END DESC;
        """,
        (
            mes_actual_desde,
            fecha_hasta,
            mes_actual_desde,
            fecha_hasta,
            mes_anterior_desde,
            mes_anterior_hasta,
            mes_anterior_desde,
            mes_anterior_hasta,
            mes_actual_desde,
            fecha_hasta,
            mes_actual_desde,
            fecha_hasta,
            *cliente_ids,
            mes_actual_desde,
            fecha_hasta,
            limite_productos,
        ),
    )
    caidos = read_sql(
        f"""
        SET NOCOUNT ON;
        WITH actual AS (
            SELECT
                fi.id_producto,
                {product_expr} AS producto,
                SUM({_signed_item_total("f", "total").replace("f.total", "fi.total")}) AS venta_mes
            FROM dbo.cli_factura_item fi
            INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
            LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.id_cliente IN ({cliente_placeholders})
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
              {_commercial_product_filter(product_expr)}
            GROUP BY fi.id_producto, {product_expr}
        ),
        anterior AS (
            SELECT
                fi.id_producto,
                {product_expr} AS producto,
                SUM({_signed_item_total("f", "total").replace("f.total", "fi.total")}) AS venta_mes_anterior
            FROM dbo.cli_factura_item fi
            INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
            LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.id_cliente IN ({cliente_placeholders})
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
              {_commercial_product_filter(product_expr)}
            GROUP BY fi.id_producto, {product_expr}
        )
        SELECT TOP (?)
            p.producto,
            ISNULL(a.venta_mes, 0) AS venta_mes,
            p.venta_mes_anterior,
            ISNULL(a.venta_mes, 0) - p.venta_mes_anterior AS variacion
        FROM anterior p
        LEFT JOIN actual a ON a.id_producto = p.id_producto
        WHERE ISNULL(a.venta_mes, 0) < p.venta_mes_anterior * 0.8
        ORDER BY variacion ASC;
        """,
        (
            *cliente_ids,
            mes_actual_desde,
            fecha_hasta,
            *cliente_ids,
            mes_anterior_desde,
            mes_anterior_hasta,
            limite_productos,
        ),
    )
    return resumen, productos, caidos


def _estrategia_cliente_from_frames(
    cliente: str,
    actual: pd.DataFrame,
    anterior: pd.DataFrame,
    limite_productos: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    actual_cliente = actual[actual["cliente"].astype(str) == cliente].copy()
    anterior_cliente = anterior[anterior["cliente"].astype(str) == cliente].copy()
    venta_mes = actual_cliente["total_firmado"].sum() if not actual_cliente.empty else 0
    venta_mes_anterior = anterior_cliente["total_firmado"].sum() if not anterior_cliente.empty else 0
    resumen = pd.DataFrame(
        {
            "venta_mes": [venta_mes],
            "venta_mes_anterior": [venta_mes_anterior],
            "comprobantes_mes": [len(actual_cliente)],
            "ultima_compra": [actual_cliente["fecha"].max().date() if not actual_cliente.empty else None],
        }
    )

    items = _snapshot_factura_items()

    def product_sales(facturas: pd.DataFrame, qty_name: str, total_name: str) -> pd.DataFrame:
        if facturas.empty:
            return pd.DataFrame(columns=["id_producto", "producto", qty_name, total_name])
        base = facturas[["id_facturacion", "tipo"]].merge(items, on="id_facturacion", how="inner")
        sign = _negative_document_mask(base["tipo"]).map(lambda is_negative: -1 if is_negative else 1)
        base[qty_name] = _to_numeric_amount(base["cantidad"]) * sign
        base[total_name] = _to_numeric_amount(base["total"]) * sign
        base["producto"] = base["producto"].fillna("")
        empty_product = base["producto"] == ""
        base.loc[empty_product, "producto"] = "Producto " + base.loc[empty_product, "id_producto"].astype(str)
        base = _filter_commercial_products(base)
        return (
            base.groupby(["id_producto", "producto"], as_index=False)
            .agg(**{qty_name: (qty_name, "sum"), total_name: (total_name, "sum")})
        )

    productos_base = product_sales(actual_cliente, "cantidad", "total")
    if productos_base.empty:
        productos_base = product_sales(anterior_cliente, "cantidad", "total")
    productos = productos_base.sort_values("total", ascending=False).head(limite_productos).loc[
        :, ["producto", "cantidad", "total"]
    ]
    actuales = product_sales(actual_cliente, "cantidad_mes", "venta_mes")
    anteriores = product_sales(anterior_cliente, "cantidad_mes_anterior", "venta_mes_anterior")
    if anteriores.empty:
        caidos = pd.DataFrame(columns=["producto", "venta_mes", "venta_mes_anterior", "variacion"])
    else:
        caidos = anteriores.merge(actuales, on=["id_producto", "producto"], how="left")
        caidos["venta_mes"] = caidos["venta_mes"].fillna(0)
        caidos["variacion"] = caidos["venta_mes"] - caidos["venta_mes_anterior"]
        caidos = caidos[caidos["venta_mes"] < caidos["venta_mes_anterior"] * 0.8]
        caidos = caidos.sort_values("variacion").head(limite_productos)
        caidos = caidos.loc[:, ["producto", "venta_mes", "venta_mes_anterior", "variacion"]]
    return resumen, productos, caidos


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


def export_facturas_snapshot(months_back: int = 24) -> pd.DataFrame:
    return read_sql(
        """
        SET NOCOUNT ON;
        SELECT
            id_facturacion,
            numero,
            CAST(fecha AS datetime) AS fecha,
            tipo,
            tipo_comprobante,
            id_cliente,
            COALESCE(NULLIF(cliente, ''), CONCAT('Cliente ', id_cliente)) AS cliente,
            COALESCE(NULLIF(zona, ''), 'Sin zona') AS zona,
            CAST(total AS decimal(18, 2)) AS total,
            CAST(subtotal AS decimal(18, 2)) AS subtotal,
            CAST(autorizado AS bit) AS autorizado
        FROM dbo.cli_factura
        WHERE ISNULL(Anulado, 0) = 0
          AND ISNULL(autorizado, 0) = 1
          AND fecha >= DATEADD(MONTH, -?, CAST(GETDATE() AS date))
          AND COALESCE(NULLIF(zona, ''), 'Sin zona') NOT IN ('PROVEEDORES')
          AND tipo IN ('FC', 'NC', 'ND');
        """,
        (months_back,),
    )


def export_factura_items_snapshot(months_back: int = 24) -> pd.DataFrame:
    product_expr = _product_name_expr("fi", "p")
    return read_sql(
        f"""
        SET NOCOUNT ON;
        SELECT
            fi.id_facturacion,
            fi.id_producto,
            {product_expr} AS producto,
            COALESCE(NULLIF(fi.marca, ''), '') AS marca,
            CAST(fi.cantidad AS decimal(18, 2)) AS cantidad,
            CAST(fi.total AS decimal(18, 2)) AS total
        FROM dbo.cli_factura_item fi
        INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
        LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
        WHERE ISNULL(f.Anulado, 0) = 0
          AND ISNULL(f.autorizado, 0) = 1
          AND f.fecha >= DATEADD(MONTH, -?, CAST(GETDATE() AS date))
          AND COALESCE(NULLIF(f.zona, ''), 'Sin zona') NOT IN ('PROVEEDORES')
          {_commercial_product_filter(product_expr)}
          AND f.tipo IN ('FC', 'NC', 'ND');
        """,
        (months_back,),
    )


def export_pedido_items_snapshot(months_back: int = 24) -> pd.DataFrame:
    return read_sql(
        """
        SET NOCOUNT ON;
        SELECT
            p.id_pedido,
            CAST(p.fecha AS datetime) AS fecha,
            p.tipo,
            p.numero,
            COALESCE(NULLIF(p.cliente, ''), CONCAT('Cliente ', p.id_cliente)) AS cliente,
            COALESCE(NULLIF(p.zona, ''), 'Sin zona') AS zona,
            pi.id_producto,
            COALESCE(NULLIF(pi.descripcion, ''), CONCAT('Producto ', pi.id_producto)) AS producto,
            COALESCE(NULLIF(pi.marca, ''), '') AS marca,
            CAST(pi.cantidad AS decimal(18, 2)) AS cantidad,
            CAST(pi.total AS decimal(18, 2)) AS total
        FROM dbo.pro_pedido p
        INNER JOIN dbo.pro_pedido_item pi ON pi.id_pedido = p.id_pedido
        WHERE ISNULL(p.Anulado, 0) = 0
          AND p.fecha >= DATEADD(MONTH, -?, CAST(GETDATE() AS date))
          AND COALESCE(NULLIF(p.zona, ''), 'Sin zona') NOT IN ('PROVEEDORES')
          AND p.tipo IN ('P', 'PD');
        """,
        (months_back,),
    )


def export_clientes_snapshot() -> pd.DataFrame:
    return read_sql(
        """
        SET NOCOUNT ON;
        SELECT DISTINCT
            c.id_cliente,
            COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente)) AS cliente,
            COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') AS zona
        FROM dbo.cli_cliente c
        INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
        LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
        WHERE ISNULL(c.activo, 0) = 1
          AND ISNULL(cs.activo, 0) = 1
          AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') NOT IN ('PROVEEDORES')
        ORDER BY cliente;
        """
    )


def export_creditos_snapshot(meses_venta: int = 12, meses_pago: int = 24) -> pd.DataFrame:
    signed_balance = _signed_balance("f", "saldo")
    raw = read_sql(
        f"""
        SET NOCOUNT ON;
        WITH clientes AS (
            SELECT DISTINCT
                c.id_cliente,
                COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente)) AS cliente,
                COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') AS zona
            FROM dbo.cli_cliente c
            INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
            LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
            WHERE ISNULL(c.activo, 0) = 1
              AND ISNULL(cs.activo, 0) = 1
              AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') NOT IN ('PROVEEDORES')
        ),
        ventas AS (
            SELECT
                f.id_cliente,
                ISNULL(SUM({_signed_total("f", "total")}), 0) AS monto_facturado
            FROM dbo.cli_factura f
            INNER JOIN clientes c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.fecha >= DATEADD(month, -?, GETDATE())
              {_commercial_zone_filter("f")}
              {_commercial_document_filter("f")}
            GROUP BY f.id_cliente
        ),
        pagos AS (
            SELECT
                f.id_cliente,
                COUNT(*) AS facturas_cobradas,
                AVG(CAST(DATEDIFF(day, f.fecha, f.fecha_liquidacion) AS decimal(18, 2))) AS dias_promedio_pago,
                MAX(DATEDIFF(day, f.fecha, f.fecha_liquidacion)) AS peor_pago,
                SUM(CASE WHEN DATEDIFF(day, f.fecha, f.fecha_liquidacion) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) AS pagos_31_60,
                SUM(CASE WHEN DATEDIFF(day, f.fecha, f.fecha_liquidacion) > 60 THEN 1 ELSE 0 END) AS pagos_mas_60
            FROM dbo.cli_factura f
            INNER JOIN clientes c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND ISNULL(f.cobrado, 0) = 1
              AND f.fecha_liquidacion IS NOT NULL
              AND DATEDIFF(day, f.fecha, f.fecha_liquidacion) >= 0
              AND f.fecha >= DATEADD(month, -?, GETDATE())
              {_commercial_zone_filter("f")}
              {_credit_document_filter("f")}
            GROUP BY f.id_cliente
        ),
        deuda AS (
            SELECT
                f.id_cliente,
                ISNULL(SUM(CASE WHEN f.saldo <> 0 THEN {signed_balance} ELSE 0 END), 0) AS saldo_actual,
                ISNULL(SUM(CASE WHEN f.saldo <> 0
                    AND CAST(COALESCE(f.fecha_vencimiento, f.fecha) AS date) < CAST(GETDATE() AS date)
                    THEN {signed_balance} ELSE 0 END), 0) AS saldo_vencido,
                ISNULL(MAX(CASE WHEN f.saldo <> 0
                    THEN DATEDIFF(day, COALESCE(f.fecha_vencimiento, f.fecha), GETDATE())
                    ELSE 0 END), 0) AS atraso_actual
            FROM dbo.cli_factura f
            INNER JOIN clientes c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {_authorized_invoice_filter("f")}
              AND f.saldo <> 0
              {_commercial_zone_filter("f")}
              {_balance_document_filter("f")}
            GROUP BY f.id_cliente
        )
        SELECT
            c.cliente,
            c.zona,
            COALESCE(v.monto_facturado, 0) AS monto_facturado,
            COALESCE(d.saldo_actual, 0) AS saldo_actual,
            COALESCE(d.saldo_vencido, 0) AS saldo_vencido,
            COALESCE(d.atraso_actual, 0) AS atraso_actual,
            CASE
                WHEN COALESCE(p.facturas_cobradas, 0) < 3 AND COALESCE(d.saldo_actual, 0) <= 0 THEN 'Sin historial - limpio'
                WHEN COALESCE(p.facturas_cobradas, 0) < 3 AND COALESCE(d.saldo_vencido, 0) > 0 THEN 'Sin historial - riesgo inicial'
                WHEN COALESCE(p.facturas_cobradas, 0) < 3 AND COALESCE(d.saldo_actual, 0) > 0 THEN 'Sin historial - observar'
                WHEN p.dias_promedio_pago <= 7 AND 100.0 * (p.pagos_31_60 + p.pagos_mas_60) / NULLIF(p.facturas_cobradas, 0) <= 10 THEN 'Bueno'
                WHEN p.dias_promedio_pago <= 20
                    AND 100.0 * (p.pagos_31_60 + p.pagos_mas_60) / NULLIF(p.facturas_cobradas, 0) <= 20
                    AND 100.0 * p.pagos_mas_60 / NULLIF(p.facturas_cobradas, 0) <= 10 THEN 'Normal'
                WHEN 100.0 * (p.pagos_31_60 + p.pagos_mas_60) / NULLIF(p.facturas_cobradas, 0) >= 70
                    AND COALESCE(d.saldo_vencido, 0) > 0 THEN 'Riesgoso'
                WHEN p.dias_promedio_pago <= 45 OR 100.0 * (p.pagos_31_60 + p.pagos_mas_60) / NULLIF(p.facturas_cobradas, 0) <= 45 THEN 'Lento habitual'
                WHEN p.dias_promedio_pago <= 70 OR 100.0 * p.pagos_mas_60 / NULLIF(p.facturas_cobradas, 0) <= 35 THEN 'Riesgoso'
                ELSE 'Malo'
            END AS segmento_pago
        FROM clientes c
        LEFT JOIN ventas v ON v.id_cliente = c.id_cliente
        LEFT JOIN pagos p ON p.id_cliente = c.id_cliente
        LEFT JOIN deuda d ON d.id_cliente = c.id_cliente
        ORDER BY c.cliente;
        """,
        (meses_venta, meses_pago),
    )
    return _credit_profile_from_raw(raw, meses_venta)


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
