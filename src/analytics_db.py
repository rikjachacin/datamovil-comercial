from __future__ import annotations

from datetime import date
import warnings

import pandas as pd
import pyodbc
import streamlit as st

from src import siscor_db


def _assert_read_only(query: str) -> None:
    """Guard the local analytics app against accidental write statements."""
    normalized = " ".join(query.upper().split())
    forbidden = (" INSERT ", " UPDATE ", " DELETE ", " MERGE ", " ALTER ", " DROP ", " TRUNCATE ", " EXEC ")
    padded = f" {normalized} "
    if any(token in padded for token in forbidden):
        raise ValueError("Bruncas Analitica solo admite consultas de lectura sobre SisCor.")


@st.cache_data(ttl=30, show_spinner=False)
def _read_sql(query: str, params: tuple[object, ...] = ()) -> pd.DataFrame:
    _assert_read_only(query)
    cfg = siscor_db.get_config()
    connection_string = (
        f"DRIVER={{{cfg.driver}}};"
        f"SERVER={cfg.server};"
        f"DATABASE={cfg.database};"
        f"UID={cfg.username};"
        f"PWD={cfg.password};"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
    )
    with pyodbc.connect(connection_string, timeout=8) as connection:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="pandas only supports SQLAlchemy connectable",
                category=UserWarning,
            )
            result = pd.read_sql(query, connection, params=params)
    return siscor_db._apply_client_name_overrides(result)


def clientes_actuales() -> pd.DataFrame:
    """Return each active customer with the seller currently assigned in SisCor."""
    return _read_sql(
        """
        SET NOCOUNT ON;
        SELECT
            CAST(c.id_cliente AS varchar(50)) AS id_cliente,
            MAX(COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente))) AS cliente,
            MAX(COALESCE(NULLIF(z.descripcion, ''), 'Sin zona')) AS zona_actual
        FROM dbo.cli_cliente c
        INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
        LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
        WHERE ISNULL(c.activo, 0) = 1
          AND ISNULL(cs.activo, 0) = 1
          AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') NOT IN ('PROVEEDORES')
        GROUP BY c.id_cliente
        ORDER BY cliente;
        """
    )


def ventas_mensuales(
    fecha_desde: date,
    fecha_hasta: date,
    zona_actual: str | None = None,
    id_cliente: str | None = None,
    zonas_permitidas: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Aggregate invoicing and product units using each customer's current zone."""
    client_filters: list[str] = []
    client_params: list[object] = []
    if zona_actual:
        client_filters.append("AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') = ?")
        client_params.append(zona_actual)
    elif zonas_permitidas:
        placeholders = ", ".join("?" for _ in zonas_permitidas)
        client_filters.append(f"AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') IN ({placeholders})")
        client_params.extend(zonas_permitidas)
    if id_cliente:
        client_filters.append("AND CAST(c.id_cliente AS varchar(50)) = ?")
        client_params.append(str(id_cliente))

    filters_sql = "\n              ".join(client_filters)
    product_expr = siscor_db._product_name_expr("fi", "p")
    signed_units = siscor_db._signed_item_total("f", "cantidad").replace("f.cantidad", "fi.cantidad")

    query = f"""
        SET NOCOUNT ON;
        WITH cartera_base AS (
            SELECT
                c.id_cliente,
                COALESCE(NULLIF(c.razon_social, ''), NULLIF(cs.nombre_comercial, ''), CONCAT('Cliente ', c.id_cliente)) AS cliente,
                COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') AS zona_actual
            FROM dbo.cli_cliente c
            INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
            LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
            WHERE ISNULL(c.activo, 0) = 1
              AND ISNULL(cs.activo, 0) = 1
              AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') NOT IN ('PROVEEDORES')
              {filters_sql}
        ),
        cartera AS (
            SELECT
                id_cliente,
                MAX(cliente) AS cliente,
                MAX(zona_actual) AS zona_actual
            FROM cartera_base
            GROUP BY id_cliente
        ),
        facturacion AS (
            SELECT
                f.id_cliente,
                CONVERT(char(7), CAST(f.fecha AS date), 120) AS mes,
                SUM({siscor_db._signed_total("f", "total")}) AS facturacion,
                COUNT(*) AS comprobantes
            FROM dbo.cli_factura f
            INNER JOIN cartera c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {siscor_db._authorized_invoice_filter("f")}
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {siscor_db._commercial_zone_filter("f")}
              {siscor_db._commercial_document_filter("f")}
            GROUP BY f.id_cliente, CONVERT(char(7), CAST(f.fecha AS date), 120)
        ),
        unidades AS (
            SELECT
                f.id_cliente,
                CONVERT(char(7), CAST(f.fecha AS date), 120) AS mes,
                SUM({signed_units}) AS unidades
            FROM dbo.cli_factura_item fi
            INNER JOIN dbo.cli_factura f ON f.id_facturacion = fi.id_facturacion
            INNER JOIN cartera c ON c.id_cliente = f.id_cliente
            LEFT JOIN dbo.pro_producto p ON p.id_producto = fi.id_producto
            WHERE ISNULL(f.Anulado, 0) = 0
              {siscor_db._authorized_invoice_filter("f")}
              AND CAST(f.fecha AS date) BETWEEN ? AND ?
              {siscor_db._commercial_zone_filter("f")}
              {siscor_db._commercial_document_filter("f")}
              {siscor_db._commercial_product_filter(product_expr)}
            GROUP BY f.id_cliente, CONVERT(char(7), CAST(f.fecha AS date), 120)
        ),
        movimientos_venta AS (
            SELECT
                COALESCE(f.id_cliente, u.id_cliente) AS id_cliente,
                COALESCE(f.mes, u.mes) AS mes,
                ISNULL(f.facturacion, 0) AS facturacion,
                ISNULL(u.unidades, 0) AS unidades,
                ISNULL(f.comprobantes, 0) AS comprobantes
            FROM facturacion f
            FULL OUTER JOIN unidades u
              ON u.id_cliente = f.id_cliente AND u.mes = f.mes
        ),
        pagos AS (
            SELECT
                oc.id_cliente,
                CONVERT(char(7), CAST(oc.fecha AS date), 120) AS mes,
                SUM(CAST(oc.total AS decimal(18, 2))) AS pagos,
                COUNT(*) AS recibos
            FROM dbo.cli_orden_cobro oc
            INNER JOIN cartera c ON c.id_cliente = oc.id_cliente
            WHERE oc.fecha_anulacion IS NULL
              AND UPPER(LTRIM(RTRIM(COALESCE(oc.tipo, '')))) IN ('R', 'RD')
              AND CAST(oc.fecha AS date) BETWEEN ? AND ?
            GROUP BY oc.id_cliente, CONVERT(char(7), CAST(oc.fecha AS date), 120)
        ),
        movimientos AS (
            SELECT
                COALESCE(v.id_cliente, p.id_cliente) AS id_cliente,
                COALESCE(v.mes, p.mes) AS mes,
                ISNULL(v.facturacion, 0) AS facturacion,
                ISNULL(v.unidades, 0) AS unidades,
                ISNULL(v.comprobantes, 0) AS comprobantes,
                ISNULL(p.pagos, 0) AS pagos,
                ISNULL(p.recibos, 0) AS recibos
            FROM movimientos_venta v
            FULL OUTER JOIN pagos p
              ON p.id_cliente = v.id_cliente AND p.mes = v.mes
        )
        SELECT
            CAST(c.id_cliente AS varchar(50)) AS id_cliente,
            c.cliente,
            c.zona_actual,
            m.mes,
            CAST(m.facturacion AS decimal(18, 2)) AS facturacion,
            CAST(m.unidades AS decimal(18, 2)) AS unidades,
            m.comprobantes,
            CAST(m.pagos AS decimal(18, 2)) AS pagos,
            m.recibos
        FROM movimientos m
        INNER JOIN cartera c ON c.id_cliente = m.id_cliente
        ORDER BY m.mes, c.zona_actual, c.cliente;
    """
    params = (
        *client_params,
        fecha_desde.isoformat(),
        fecha_hasta.isoformat(),
        fecha_desde.isoformat(),
        fecha_hasta.isoformat(),
        fecha_desde.isoformat(),
        fecha_hasta.isoformat(),
    )
    result = _read_sql(query, params)
    if result.empty:
        return pd.DataFrame(
            columns=[
                "id_cliente",
                "cliente",
                "zona_actual",
                "mes",
                "facturacion",
                "unidades",
                "comprobantes",
                "pagos",
                "recibos",
            ]
        )
    for column in ("facturacion", "unidades", "comprobantes", "pagos", "recibos"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    result["id_cliente"] = result["id_cliente"].astype(str).str.strip()
    return result


def deuda_actual(
    zona_actual: str | None = None,
    id_cliente: str | None = None,
    zonas_permitidas: tuple[str, ...] = (),
) -> float:
    """Return today's positive outstanding balance for the current selection."""
    client_filters: list[str] = []
    params: list[object] = []
    if zona_actual:
        client_filters.append("AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') = ?")
        params.append(zona_actual)
    elif zonas_permitidas:
        placeholders = ", ".join("?" for _ in zonas_permitidas)
        client_filters.append(f"AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') IN ({placeholders})")
        params.extend(zonas_permitidas)
    if id_cliente:
        client_filters.append("AND CAST(c.id_cliente AS varchar(50)) = ?")
        params.append(str(id_cliente))

    filters_sql = "\n              ".join(client_filters)
    signed_balance = siscor_db._signed_balance("f", "saldo")
    result = _read_sql(
        f"""
        SET NOCOUNT ON;
        WITH cartera_base AS (
            SELECT c.id_cliente
            FROM dbo.cli_cliente c
            INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
            LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
            WHERE ISNULL(c.activo, 0) = 1
              AND ISNULL(cs.activo, 0) = 1
              AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') NOT IN ('PROVEEDORES')
              {filters_sql}
            GROUP BY c.id_cliente
        ),
        saldos AS (
            SELECT
                f.id_cliente,
                SUM({signed_balance}) AS saldo_actual
            FROM dbo.cli_factura f
            INNER JOIN cartera_base c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {siscor_db._authorized_invoice_filter("f")}
              AND f.saldo <> 0
              {siscor_db._commercial_zone_filter("f")}
              {siscor_db._balance_document_filter("f")}
            GROUP BY f.id_cliente
        )
        SELECT COALESCE(SUM(CASE WHEN saldo_actual > 0 THEN saldo_actual ELSE 0 END), 0) AS deuda_actual
        FROM saldos;
        """,
        tuple(params),
    )
    if result.empty:
        return 0.0
    return float(pd.to_numeric(result.iloc[0]["deuda_actual"], errors="coerce") or 0.0)


def resumen_periodos(
    periodos: tuple[tuple[str, date, date], ...],
    zona_actual: str | None = None,
    id_cliente: str | None = None,
    zonas_permitidas: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Aggregate comparable sales, units and payments in one read-only query."""
    columns = ["periodo", "facturacion", "unidades", "pagos"]
    if not periodos:
        return pd.DataFrame(columns=columns)

    client_filters: list[str] = []
    params: list[object] = []
    if zona_actual:
        client_filters.append("AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') = ?")
        params.append(zona_actual)
    elif zonas_permitidas:
        placeholders = ", ".join("?" for _ in zonas_permitidas)
        client_filters.append(f"AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') IN ({placeholders})")
        params.extend(zonas_permitidas)
    if id_cliente:
        client_filters.append("AND CAST(c.id_cliente AS varchar(50)) = ?")
        params.append(str(id_cliente))

    period_rows = []
    for name, start, end in periodos:
        period_rows.append("SELECT ? AS periodo, CAST(? AS date) AS fecha_desde, CAST(? AS date) AS fecha_hasta")
        params.extend((name, start.isoformat(), end.isoformat()))

    filters_sql = "\n              ".join(client_filters)
    periods_sql = "\n            UNION ALL\n            ".join(period_rows)
    product_expr = siscor_db._product_name_expr("fi", "p")
    signed_units = siscor_db._signed_item_total("f", "cantidad").replace("f.cantidad", "fi.cantidad")
    result = _read_sql(
        f"""
        SET NOCOUNT ON;
        WITH cartera_base AS (
            SELECT c.id_cliente
            FROM dbo.cli_cliente c
            INNER JOIN dbo.cli_sucursal cs ON cs.id_cliente = c.id_cliente
            LEFT JOIN dbo.tg_zona z ON z.id_zona = cs.id_zona
            WHERE ISNULL(c.activo, 0) = 1
              AND ISNULL(cs.activo, 0) = 1
              AND COALESCE(NULLIF(z.descripcion, ''), 'Sin zona') NOT IN ('PROVEEDORES')
              {filters_sql}
            GROUP BY c.id_cliente
        ),
        periodos AS (
            {periods_sql}
        ),
        facturacion AS (
            SELECT p.periodo, SUM({siscor_db._signed_total("f", "total")}) AS facturacion
            FROM periodos p
            INNER JOIN dbo.cli_factura f ON CAST(f.fecha AS date) BETWEEN p.fecha_desde AND p.fecha_hasta
            INNER JOIN cartera_base c ON c.id_cliente = f.id_cliente
            WHERE ISNULL(f.Anulado, 0) = 0
              {siscor_db._authorized_invoice_filter("f")}
              {siscor_db._commercial_zone_filter("f")}
              {siscor_db._commercial_document_filter("f")}
            GROUP BY p.periodo
        ),
        unidades AS (
            SELECT p.periodo, SUM({signed_units}) AS unidades
            FROM periodos p
            INNER JOIN dbo.cli_factura f ON CAST(f.fecha AS date) BETWEEN p.fecha_desde AND p.fecha_hasta
            INNER JOIN cartera_base c ON c.id_cliente = f.id_cliente
            INNER JOIN dbo.cli_factura_item fi ON fi.id_facturacion = f.id_facturacion
            LEFT JOIN dbo.pro_producto pprod ON pprod.id_producto = fi.id_producto
            WHERE ISNULL(f.Anulado, 0) = 0
              {siscor_db._authorized_invoice_filter("f")}
              {siscor_db._commercial_zone_filter("f")}
              {siscor_db._commercial_document_filter("f")}
              {siscor_db._commercial_product_filter(product_expr.replace("p.", "pprod."))}
            GROUP BY p.periodo
        ),
        pagos AS (
            SELECT p.periodo, SUM(CAST(oc.total AS decimal(18, 2))) AS pagos
            FROM periodos p
            INNER JOIN dbo.cli_orden_cobro oc ON CAST(oc.fecha AS date) BETWEEN p.fecha_desde AND p.fecha_hasta
            INNER JOIN cartera_base c ON c.id_cliente = oc.id_cliente
            WHERE oc.fecha_anulacion IS NULL
              AND UPPER(LTRIM(RTRIM(COALESCE(oc.tipo, '')))) IN ('R', 'RD')
            GROUP BY p.periodo
        )
        SELECT
            p.periodo,
            COALESCE(f.facturacion, 0) AS facturacion,
            COALESCE(u.unidades, 0) AS unidades,
            COALESCE(pg.pagos, 0) AS pagos
        FROM periodos p
        LEFT JOIN facturacion f ON f.periodo = p.periodo
        LEFT JOIN unidades u ON u.periodo = p.periodo
        LEFT JOIN pagos pg ON pg.periodo = p.periodo;
        """,
        tuple(params),
    )
    for column in ("facturacion", "unidades", "pagos"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    return result.loc[:, columns]


def clear_cache() -> None:
    _read_sql.clear()
