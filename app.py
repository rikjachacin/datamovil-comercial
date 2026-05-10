from __future__ import annotations

from datetime import timedelta
import traceback

import pandas as pd
import plotly.express as px
import streamlit as st

from src import auth
from src import objectives
from src import siscor_db


st.set_page_config(
    page_title="DataMovil Comercial",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        --dm-bg: #f4f7fb;
        --dm-panel: #ffffff;
        --dm-border: #d8e1ed;
        --dm-border-strong: #b9c8da;
        --dm-text: #182536;
        --dm-muted: #66758a;
        --dm-accent: #0f7b6c;
        --dm-accent-2: #1f5eff;
        --dm-sidebar: #f8fbfd;
    }

    .stApp {
        background:
            linear-gradient(180deg, #eef5fb 0%, #f7f9fc 260px, #f7f9fc 100%);
        color: var(--dm-text);
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    [data-testid="stSidebar"] {
        background:
            linear-gradient(180deg, #ffffff 0%, var(--dm-sidebar) 62%, #eef5f7 100%);
        border-right: 1px solid var(--dm-border);
        box-shadow: 8px 0 28px rgba(20, 36, 58, 0.06);
    }

    [data-testid="stSidebar"] section {
        padding-top: 1.3rem;
    }

    [data-testid="stSidebar"] h3 {
        font-size: 16px;
        font-weight: 800;
        color: var(--dm-text);
        margin-bottom: 0.45rem;
    }

    [data-testid="stSidebar"] h3::before {
        content: "";
        display: inline-block;
        width: 4px;
        height: 16px;
        margin-right: 8px;
        border-radius: 8px;
        background: linear-gradient(180deg, var(--dm-accent), #2c74d6);
        vertical-align: -3px;
    }

    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: var(--dm-muted);
    }

    [data-testid="stSidebar"] p {
        color: var(--dm-text);
    }

    [data-testid="stSidebar"] hr {
        margin: 1.35rem 0;
        border-color: var(--dm-border);
    }

    .dm-header {
        border: 1px solid var(--dm-border);
        background: linear-gradient(135deg, #ffffff 0%, #eef7f5 48%, #eef3ff 100%);
        border-radius: 8px;
        padding: 20px 24px;
        margin-bottom: 18px;
        box-shadow: 0 10px 28px rgba(25, 40, 64, 0.08);
    }

    .dm-title {
        font-size: 34px;
        font-weight: 750;
        line-height: 1.1;
        margin: 0;
        color: var(--dm-text);
    }

    .dm-subtitle {
        margin-top: 8px;
        color: var(--dm-muted);
        font-size: 15px;
    }

    [data-testid="stMetric"] {
        background: var(--dm-panel);
        border: 1px solid var(--dm-border);
        border-radius: 8px;
        padding: 16px 18px;
        box-shadow: 0 8px 22px rgba(20, 36, 58, 0.06);
    }

    [data-testid="stMetricLabel"] {
        color: var(--dm-muted);
        font-weight: 650;
    }

    [data-testid="stMetricValue"] {
        color: var(--dm-text);
        font-size: 26px;
    }

    .stButton button {
        border-radius: 8px;
        border: 1px solid var(--dm-border-strong);
        background: #ffffff;
        color: var(--dm-text);
        font-weight: 650;
        transition: all 120ms ease;
    }

    .stButton button:hover {
        border-color: var(--dm-accent);
        color: var(--dm-accent);
        box-shadow: 0 8px 18px rgba(15, 123, 108, 0.12);
    }

    [data-baseweb="input"],
    [data-baseweb="select"],
    [data-baseweb="popover"] {
        border-radius: 8px;
    }

    [data-baseweb="input"] {
        border-color: var(--dm-border);
    }

    .dm-card {
        min-height: 178px;
        background: var(--dm-panel);
        border: 1px solid var(--dm-border);
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 8px 22px rgba(20, 36, 58, 0.06);
    }

    .dm-card-label {
        color: #0f766e;
        font-size: 12px;
        font-weight: 750;
        text-transform: uppercase;
        margin-bottom: 8px;
    }

    .dm-card-value {
        color: var(--dm-text);
        font-size: 20px;
        font-weight: 750;
        line-height: 1.25;
        margin-bottom: 10px;
    }

    .dm-card-note {
        color: var(--dm-muted);
        font-size: 13px;
        line-height: 1.35;
        margin-top: 6px;
    }

    div[data-testid="stPlotlyChart"],
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--dm-border);
        border-radius: 8px;
        background: var(--dm-panel);
        padding: 8px;
        box-shadow: 0 8px 22px rgba(20, 36, 58, 0.05);
    }

    h2, h3 {
        color: var(--dm-text);
        letter-spacing: 0;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid var(--dm-border);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def money(value: object) -> str:
    if pd.isna(value):
        return "$ 0"
    return f"$ {float(value):,.0f}".replace(",", ".")


def number(value: object) -> str:
    if pd.isna(value):
        return "0"
    return f"{float(value):,.0f}".replace(",", ".")


def percent(value: object) -> str:
    if pd.isna(value):
        return "0,0 %"
    return f"{float(value) * 100:,.1f} %".replace(",", "X").replace(".", ",").replace("X", ".")


def numeric_value(value: object) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return 0.0 if pd.isna(numeric) else float(numeric)


def seller_action_message(performance_row: pd.Series | None, clients: pd.DataFrame, products: pd.DataFrame) -> str:
    if performance_row is None:
        return "No hay objetivo asignado para esta zona. Revisar configuracion antes de evaluar desempeno."

    status = str(performance_row["estado"])
    if status == "En ritmo":
        base = "Vas en ritmo. Mantene frecuencia de visita y cuida reposicion en clientes activos."
    elif status == "Cerca":
        base = "Estas cerca del ritmo. Un empuje corto puede recuperar la brecha de este mes."
    else:
        base = "Necesitas recuperar ritmo. Prioriza visitas de clientes caidos y productos con baja frente al mes anterior."

    if not clients.empty:
        base += f" Primer cliente a revisar: {clients.iloc[0]['cliente']}."
    if not products.empty:
        base += f" Producto foco: {products.iloc[0]['producto']}."
    return base


def client_strategy_message(cliente: str, resumen: pd.Series, caidos: pd.DataFrame) -> str:
    venta_mes = numeric_value(resumen.get("venta_mes"))
    venta_anterior = numeric_value(resumen.get("venta_mes_anterior"))
    variacion = venta_mes - venta_anterior

    if venta_anterior <= 0 and venta_mes > 0:
        message = f"{cliente} aparece activo este mes. Conviene sostener frecuencia y revisar productos complementarios."
    elif venta_mes <= 0 and venta_anterior > 0:
        message = f"{cliente} compro el mes anterior y este mes no registra compra. Prioridad alta para contacto o visita."
    elif variacion < 0:
        message = f"{cliente} bajo {money(abs(variacion))} frente al mes anterior. Enfocar la visita en recuperar rotacion."
    else:
        message = f"{cliente} viene por encima del mes anterior. Buscar ampliar ticket con productos complementarios."

    if not caidos.empty:
        message += f" Producto a recuperar: {caidos.iloc[0]['producto']}."
    return message


def build_action_radar(
    performance: pd.DataFrame,
    clients: pd.DataFrame,
    products: pd.DataFrame,
    limit: int = 12,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    if not performance.empty and "tiene_objetivo" in performance.columns:
        scoped = performance[performance["tiene_objetivo"]].copy()
        scoped = scoped[scoped["ritmo"] < 1].sort_values(["ritmo", "brecha_esperada"], ascending=[True, True])
        for _, row in scoped.head(5).iterrows():
            ritmo = numeric_value(row["ritmo"])
            rows.append(
                {
                    "prioridad": "Alta" if ritmo < 0.85 else "Media",
                    "frente": "Zona",
                    "zona": row["zona"],
                    "foco": f"Ritmo {percent(ritmo)}",
                    "impacto_estimado": abs(numeric_value(row["brecha_esperada"])),
                    "accion": "Acompanamiento diario y foco en clientes de mayor potencial",
                }
            )

    if not clients.empty:
        client_rows = clients.copy()
        client_rows["impacto"] = client_rows["variacion"].map(lambda value: abs(numeric_value(value)))
        for _, row in client_rows.sort_values("impacto", ascending=False).head(5).iterrows():
            rows.append(
                {
                    "prioridad": "Alta" if numeric_value(row["impacto"]) >= 1_000_000 else "Media",
                    "frente": "Cliente",
                    "zona": row.get("zona", "Equipo"),
                    "foco": row["cliente"],
                    "impacto_estimado": numeric_value(row["impacto"]),
                    "accion": row.get("accion", "Contactar y recuperar compra"),
                }
            )

    if not products.empty:
        product_rows = products.copy()
        product_rows["impacto"] = product_rows["variacion"].map(lambda value: abs(numeric_value(value)))
        for _, row in product_rows.sort_values("impacto", ascending=False).head(5).iterrows():
            rows.append(
                {
                    "prioridad": "Media",
                    "frente": "Producto",
                    "zona": "Equipo",
                    "foco": row["producto"],
                    "impacto_estimado": numeric_value(row["impacto"]),
                    "accion": row.get("accion", "Impulsar en visitas y reposicion"),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["prioridad", "frente", "zona", "foco", "impacto_estimado", "accion"])

    radar = pd.DataFrame(rows)
    priority_order = {"Alta": 0, "Media": 1, "Baja": 2}
    radar["orden"] = radar["prioridad"].map(priority_order).fillna(9)
    radar = radar.sort_values(["orden", "impacto_estimado"], ascending=[True, False]).head(limit)
    return radar.drop(columns=["orden"])


def build_daily_plan(radar: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    if radar.empty:
        return pd.DataFrame(columns=["orden", "prioridad", "titulo", "detalle", "accion", "impacto_estimado"])

    labels = ["Primero", "Segundo", "Tercero"]
    plan_rows: list[dict[str, object]] = []
    for idx, (_, row) in enumerate(radar.head(limit).iterrows()):
        frente = str(row["frente"])
        foco = str(row["foco"])
        zona = str(row["zona"])
        if frente == "Zona":
            titulo = f"Levantar {zona}"
            detalle = foco
        elif frente == "Cliente":
            titulo = "Recuperar cliente"
            detalle = f"{zona} - {foco}"
        else:
            titulo = "Empujar producto"
            detalle = foco

        plan_rows.append(
            {
                "orden": labels[idx],
                "prioridad": row["prioridad"],
                "titulo": titulo,
                "detalle": detalle,
                "accion": row["accion"],
                "impacto_estimado": row["impacto_estimado"],
            }
        )
    return pd.DataFrame(plan_rows)


def build_executive_brief(
    period_label: str,
    total_sales: float,
    total_goal: float,
    team_pace: float,
    projected_gap: float,
    daily_needed: float,
    plan: pd.DataFrame,
) -> str:
    goal_text = money(total_goal) if total_goal else "sin objetivo cargado"
    lines = [
        f"Resumen comercial {period_label}",
        f"Ventas acumuladas: {money(total_sales)} sobre objetivo {goal_text}.",
        f"Ritmo del equipo: {percent(team_pace)}.",
        f"Brecha proyectada al cierre: {money(projected_gap)}.",
        f"Venta diaria necesaria para llegar al objetivo: {money(daily_needed)}.",
    ]

    if not plan.empty:
        lines.append("Prioridades de hoy:")
        for _, row in plan.iterrows():
            lines.append(
                f"- {row['orden']}: {row['titulo']} | {row['detalle']} | "
                f"{row['accion']} | impacto {money(row['impacto_estimado'])}."
            )
    else:
        lines.append("No hay prioridades criticas detectadas para hoy.")

    return "\n".join(lines)


def login_screen() -> None:
    st.markdown(
        """
        <div class="dm-header">
            <div class="dm-title">DataMovil Comercial</div>
            <div class="dm-subtitle">Ingreso privado al panel comercial</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    login_col, _ = st.columns([0.42, 0.58])
    with login_col:
        st.subheader("Acceso")
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contrasena", type="password")
            submitted = st.form_submit_button("Ingresar", use_container_width=True)

        if submitted:
            user = auth.authenticate(username, password)
            if user is None:
                st.error("Usuario o contrasena incorrectos.")
            else:
                st.session_state["user"] = user
                st.rerun()


if "user" not in st.session_state:
    login_screen()
    st.stop()

current_user: auth.User = st.session_state["user"]

st.markdown(
    """
    <div class="dm-header">
        <div class="dm-title">DataMovil Comercial</div>
        <div class="dm-subtitle">Panel comercial conectado a datos reales de SisCor</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Usuario")
    st.write(current_user.name)
    st.caption("Administrador" if current_user.is_admin else "Zona asignada")
    if st.button("Cerrar sesion", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.divider()
    if siscor_db.data_mode() == "snapshot":
        st.subheader("Datos")
        if siscor_db.using_sample_snapshot():
            st.caption("Modo prueba")
        else:
            st.caption("Modo snapshot real")
    else:
        st.subheader("Conexion SisCor")
        cfg = siscor_db.get_config()
        st.caption(f"{cfg.database} en {cfg.server}")

        if st.button("Probar conexion", use_container_width=True):
            st.dataframe(siscor_db.ping(), use_container_width=True, hide_index=True)

try:
    limites = siscor_db.month_options().iloc[0]
    fecha_maxima = pd.to_datetime(limites["fecha_maxima"]).date()
    fecha_minima = pd.to_datetime(limites["fecha_minima"]).date()
    zonas_df = siscor_db.zonas()
except Exception as exc:
    snapshot_error = getattr(siscor_db, "SnapshotDataMissing", RuntimeError)
    if siscor_db.data_mode() == "snapshot" and isinstance(exc, snapshot_error):
        st.warning("La aplicacion ya esta publicada, pero todavia no tiene datos cargados.")
        st.code(str(exc))
        st.info(
            "En Streamlit Cloud estamos usando modo snapshot para no conectar directo a SisCor. "
            "Falta definir una fuente segura para subir los datos exportados sin publicar informacion comercial."
        )
        st.stop()

    st.error("No pude leer los datos comerciales.")
    st.code("".join(traceback.format_exception_only(type(exc), exc)).strip())
    st.stop()

if siscor_db.using_sample_snapshot():
    st.warning("Vista de prueba con datos ficticios. No corresponde a ventas reales de SisCor.")

mes_actual_desde = max(fecha_minima, pd.Timestamp(fecha_maxima).replace(day=1).date())
mes_anterior_desde = (pd.Timestamp(mes_actual_desde) - pd.DateOffset(months=1)).date()
mes_anterior_hasta = (pd.Timestamp(mes_actual_desde) - pd.Timedelta(days=1)).date()
mes_objetivo = objectives.month_key(fecha_maxima)
avance_mes = objectives.month_progress(fecha_maxima)
dias_restantes = objectives.remaining_days(fecha_maxima)
try:
    objetivos_df = objectives.load_objectives()
except Exception as exc:
    st.error("No pude leer la tabla de objetivos.")
    st.code("".join(traceback.format_exception_only(type(exc), exc)).strip())
    objetivos_df = pd.DataFrame(columns=["mes", "zona", "objetivo"])

zonas_objetivo = tuple(
    objetivos_df.loc[objetivos_df["mes"] == mes_objetivo, "zona"].dropna().astype(str)
)
if zonas_objetivo:
    zonas_df = zonas_df[zonas_df["zona"].isin(zonas_objetivo)].copy()

with st.sidebar:
    st.subheader("Segmentadores")
    vista_vendedor_activa = not current_user.is_admin
    if current_user.is_admin:
        modo_vista = st.selectbox(
            "Vista",
            options=["Administrador", "Vendedor"],
            index=0,
        )
        vista_vendedor_activa = modo_vista == "Vendedor"

    periodo = st.segmented_control(
        "Periodo",
        ["Mes en curso", "Ultimos 30 dias", "Rango"],
        default="Mes en curso",
    )

    if periodo == "Mes en curso":
        fecha_desde = mes_actual_desde
        fecha_hasta = fecha_maxima
        st.caption(f"{fecha_desde:%d/%m/%Y} al {fecha_hasta:%d/%m/%Y}")
    elif periodo == "Ultimos 30 dias":
        fecha_desde = max(fecha_minima, fecha_maxima - timedelta(days=30))
        fecha_hasta = fecha_maxima
        st.caption(f"{fecha_desde:%d/%m/%Y} al {fecha_hasta:%d/%m/%Y}")
    else:
        fecha_desde = st.date_input(
            "Desde",
            value=mes_actual_desde,
            min_value=fecha_minima,
            max_value=fecha_maxima,
        )
        fecha_hasta = st.date_input(
            "Hasta",
            value=fecha_maxima,
            min_value=fecha_minima,
            max_value=fecha_maxima,
        )

    zonas_disponibles = zonas_df["zona"].dropna().astype(str).tolist()
    if current_user.is_admin and not vista_vendedor_activa:
        zona_seleccion = st.multiselect(
            "Zonas",
            options=zonas_disponibles,
            placeholder="Todas las zonas",
        )
    elif current_user.is_admin and vista_vendedor_activa:
        vendedor_simulado = st.selectbox(
            "Vendedor",
            options=zonas_disponibles,
            index=0 if zonas_disponibles else None,
            placeholder="Elegir vendedor",
        )
        zona_seleccion = [vendedor_simulado] if vendedor_simulado else []
        st.caption("Vista simulada del vendedor seleccionado")
    else:
        zona_seleccion = [zone for zone in current_user.zones if zone in zonas_disponibles]
        st.text_input("Zona", value=", ".join(zona_seleccion), disabled=True)
        if not zona_seleccion:
            st.warning("Tu usuario no tiene una zona valida asignada.")

zonas_filtro = tuple(str(value) for value in zona_seleccion)
if not zonas_filtro and zonas_objetivo:
    zonas_filtro = zonas_objetivo

if fecha_desde > fecha_hasta:
    st.warning("La fecha desde no puede ser mayor que la fecha hasta.")
    st.stop()

desde_sql = fecha_desde.isoformat()
hasta_sql = fecha_hasta.isoformat()

kpi_df = siscor_db.kpis(desde_sql, hasta_sql, zonas_filtro).iloc[0]

if vista_vendedor_activa:
    if current_user.is_admin:
        zona_preview = ", ".join(zonas_filtro) if zonas_filtro else "Sin zona"
        st.info(f"Vista simulada de vendedor: {zona_preview}")

    ventas_mes_vendedor = siscor_db.ventas_por_zona(
        mes_actual_desde.isoformat(),
        fecha_maxima.isoformat(),
        zonas_filtro,
    )
    if objetivos_df.empty:
        desempeno_vendedor = pd.DataFrame()
    else:
        desempeno_vendedor = objectives.monthly_performance(
            ventas_mes_vendedor,
            objetivos_df,
            mes_objetivo,
            avance_mes,
            dias_restantes,
        )

    vendedor_row = None if desempeno_vendedor.empty else desempeno_vendedor.iloc[0]
    clientes_vendedor = siscor_db.clientes_a_recuperar(
        mes_actual_desde.isoformat(),
        fecha_maxima.isoformat(),
        mes_anterior_desde.isoformat(),
        mes_anterior_hasta.isoformat(),
        zonas_filtro,
        limite=5,
    )
    productos_vendedor = siscor_db.productos_a_impulsar(
        mes_actual_desde.isoformat(),
        fecha_maxima.isoformat(),
        mes_anterior_desde.isoformat(),
        mes_anterior_hasta.isoformat(),
        zonas_filtro,
        limite=5,
    )
    top_clientes_vendedor = siscor_db.top_clientes(
        mes_actual_desde.isoformat(),
        fecha_maxima.isoformat(),
        zonas_filtro,
        limite=8,
    )

    st.subheader("Mi avance del mes")
    if vendedor_row is None:
        st.warning("Tu zona no tiene objetivo cargado para este mes.")
    else:
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Ventas mes", money(vendedor_row["ventas_mes"]))
        v2.metric("Objetivo", money(vendedor_row["objetivo"]))
        v3.metric("Cumplimiento", percent(vendedor_row["cumplimiento"]))
        v4.metric("Diario necesario", money(vendedor_row["venta_diaria_necesaria"]))

        r1, r2, r3 = st.columns(3)
        r1.metric("Ritmo a la fecha", percent(vendedor_row["ritmo"]))
        r2.metric("Proyeccion cierre", money(vendedor_row["proyeccion_cierre"]))
        r3.metric("Brecha objetivo", money(vendedor_row["brecha_objetivo"]))

    st.info(seller_action_message(vendedor_row, clientes_vendedor, productos_vendedor))

    tab_plan, tab_clientes_v, tab_productos_v = st.tabs(["Plan de accion", "Clientes", "Productos"])
    with tab_plan:
        st.markdown("#### Clientes a recuperar")
        st.dataframe(
            clientes_vendedor,
            use_container_width=True,
            hide_index=True,
            column_config={
                "cliente": "Cliente",
                "zona": "Zona",
                "venta_mes": st.column_config.NumberColumn("Venta mes", format="$ %.0f"),
                "venta_mes_anterior": st.column_config.NumberColumn("Mes anterior", format="$ %.0f"),
                "variacion": st.column_config.NumberColumn("Variacion", format="$ %.0f"),
                "accion": "Accion sugerida",
            },
        )
        st.markdown("#### Productos foco")
        st.dataframe(
            productos_vendedor,
            use_container_width=True,
            hide_index=True,
            column_config={
                "producto": "Producto",
                "cantidad_mes": st.column_config.NumberColumn("Cantidad mes", format="%.2f"),
                "cantidad_mes_anterior": st.column_config.NumberColumn("Cantidad anterior", format="%.2f"),
                "venta_mes": st.column_config.NumberColumn("Venta mes", format="$ %.0f"),
                "venta_mes_anterior": st.column_config.NumberColumn("Mes anterior", format="$ %.0f"),
                "variacion": st.column_config.NumberColumn("Variacion", format="$ %.0f"),
                "accion": "Accion sugerida",
            },
        )

    with tab_clientes_v:
        st.dataframe(
            top_clientes_vendedor,
            use_container_width=True,
            hide_index=True,
            column_config={
                "cliente": "Cliente",
                "total": st.column_config.NumberColumn("Total", format="$ %.0f"),
                "comprobantes": st.column_config.NumberColumn("Comprobantes", format="%d"),
            },
        )

    with tab_productos_v:
        st.dataframe(
            siscor_db.top_productos(
                mes_actual_desde.isoformat(),
                fecha_maxima.isoformat(),
                zonas_filtro,
                limite=8,
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "producto": "Producto",
                "cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
                "total": st.column_config.NumberColumn("Total", format="$ %.0f"),
            },
        )

    st.subheader("Estrategia cliente")
    clientes_opciones = sorted(
        pd.concat(
            [
                clientes_vendedor.get("cliente", pd.Series(dtype=str)),
                top_clientes_vendedor.get("cliente", pd.Series(dtype=str)),
            ],
            ignore_index=True,
        )
        .dropna()
        .astype(str)
        .unique()
    )
    cliente_seleccionado = None
    if clientes_opciones:
        cliente_seleccionado = st.selectbox(
            "Cliente",
            clientes_opciones,
            index=None,
            placeholder="Buscar cliente",
        )
    else:
        st.info("No hay clientes con movimiento suficiente para generar estrategia en este periodo.")

    if cliente_seleccionado:
        resumen_cliente, productos_cliente, caidos_cliente = siscor_db.estrategia_cliente(
            cliente_seleccionado,
            mes_actual_desde.isoformat(),
            fecha_maxima.isoformat(),
            mes_anterior_desde.isoformat(),
            mes_anterior_hasta.isoformat(),
            zonas_filtro,
        )
        resumen_row = resumen_cliente.iloc[0]
        venta_mes_cliente = numeric_value(resumen_row["venta_mes"])
        venta_anterior_cliente = numeric_value(resumen_row["venta_mes_anterior"])
        ultima_compra = resumen_row["ultima_compra"]
        ultima_compra_texto = "Sin compra" if pd.isna(ultima_compra) else str(ultima_compra)
        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Venta mes", money(venta_mes_cliente))
        ec2.metric("Mes anterior", money(venta_anterior_cliente))
        ec3.metric("Variacion", money(venta_mes_cliente - venta_anterior_cliente))
        ec4.metric("Ultima compra", ultima_compra_texto)
        st.info(client_strategy_message(cliente_seleccionado, resumen_row, caidos_cliente))

        cprod, ccaidos = st.columns(2)
        with cprod:
            st.markdown("#### Productos habituales")
            st.dataframe(
                productos_cliente,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "producto": "Producto",
                    "cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
                    "total": st.column_config.NumberColumn("Total", format="$ %.0f"),
                },
            )
        with ccaidos:
            st.markdown("#### Productos caidos")
            st.dataframe(
                caidos_cliente,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "producto": "Producto",
                    "venta_mes": st.column_config.NumberColumn("Venta mes", format="$ %.0f"),
                    "venta_mes_anterior": st.column_config.NumberColumn("Mes anterior", format="$ %.0f"),
                    "variacion": st.column_config.NumberColumn("Variacion", format="$ %.0f"),
                },
            )

    st.stop()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Ventas", money(kpi_df["total"]))
m2.metric("Comprobantes", number(kpi_df["comprobantes"]))
m3.metric("Clientes", number(kpi_df["clientes"]))
m4.metric("Ticket promedio", money(kpi_df["ticket_promedio"]))

st.divider()

ventas_objetivo = siscor_db.ventas_por_zona(
    mes_actual_desde.isoformat(),
    fecha_maxima.isoformat(),
    zonas_objetivo,
)

st.subheader("Objetivos y ritmo del mes")
desempeno_df = pd.DataFrame()
total_ventas_mes = 0.0
total_objetivo = 0.0
total_proyeccion = 0.0
venta_diaria_necesaria = 0.0
cumplimiento_total = 0.0
ritmo_total = 0.0
if objetivos_df.empty:
    st.info(
        "Falta cargar la tabla de objetivos mensual. La app espera un archivo "
        "data/objetivos.csv con columnas: mes, zona, objetivo."
    )
    st.dataframe(
        pd.DataFrame(
            {
                "mes": [mes_objetivo],
                "zona": ["CARINA"],
                "objetivo": [50000000],
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
else:
    desempeno_df = objectives.monthly_performance(
        ventas_objetivo,
        objetivos_df,
        mes_objetivo,
        avance_mes,
        dias_restantes,
    )
    desempeno_con_objetivo = desempeno_df[desempeno_df["tiene_objetivo"]].copy()
    total_ventas_mes = desempeno_con_objetivo["ventas_mes"].sum()
    total_objetivo = desempeno_con_objetivo["objetivo"].sum()
    total_objetivo_esperado = desempeno_con_objetivo["objetivo_esperado"].sum()
    total_proyeccion = desempeno_con_objetivo["proyeccion_cierre"].sum()
    venta_diaria_necesaria = desempeno_con_objetivo["venta_diaria_necesaria"].sum()
    cumplimiento_total = total_ventas_mes / total_objetivo if total_objetivo else 0
    ritmo_total = total_ventas_mes / total_objetivo_esperado if total_objetivo_esperado else 0
    zonas_en_ritmo = int((desempeno_con_objetivo["ritmo"] >= 1).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cumplimiento mensual", percent(cumplimiento_total))
    c2.metric("Ritmo esperado", percent(avance_mes))
    c3.metric("Ritmo del equipo", percent(ritmo_total))
    c4.metric("Zonas en ritmo", f"{zonas_en_ritmo}/{len(desempeno_con_objetivo)}")

    p1, p2, p3 = st.columns(3)
    p1.metric("Proyeccion de cierre", money(total_proyeccion))
    p2.metric("Brecha proyectada", money(total_proyeccion - total_objetivo))
    p3.metric("Venta diaria necesaria", money(venta_diaria_necesaria))

    insights = objectives.executive_insights(desempeno_df)
    leader = insights["leader"]
    risk = insights["risk"]

    st.markdown("#### Lectura ejecutiva")
    i1, i2, i3 = st.columns(3)
    if leader is not None:
        i1.metric(
            "Mejor ritmo",
            str(leader["zona"]),
            percent(leader["ritmo"]),
        )
    else:
        i1.metric("Mejor ritmo", "Sin datos")

    if risk is not None:
        i2.metric(
            "Mayor brecha",
            str(risk["zona"]),
            money(risk["brecha_esperada"]),
        )
    else:
        i2.metric("Mayor brecha", "Sin datos")

    i3.metric("Zonas bajo ritmo", number(insights["below_pace"]))
    st.info(str(insights["message"]))

    ranking_df = desempeno_df.copy()
    ranking_df["cumplimiento_pct"] = ranking_df["cumplimiento"] * 100
    ranking_df["ritmo_pct"] = ranking_df["ritmo"] * 100
    ranking_df = ranking_df[
        [
            "zona",
            "ventas_mes",
            "objetivo",
            "cumplimiento_pct",
            "ritmo_pct",
            "proyeccion_cierre",
            "brecha_objetivo",
            "venta_diaria_necesaria",
            "brecha_esperada",
            "tiene_objetivo",
            "estado",
        ]
    ]
    ranking_df.loc[~ranking_df["tiene_objetivo"], "estado"] = "Sin objetivo"
    st.dataframe(
        ranking_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "zona": "Zona",
            "ventas_mes": st.column_config.NumberColumn("Ventas mes", format="$ %.0f"),
            "objetivo": st.column_config.NumberColumn("Objetivo", format="$ %.0f"),
            "cumplimiento_pct": st.column_config.ProgressColumn(
                "Cumplimiento",
                min_value=0,
                max_value=100,
                format="%.1f %%",
            ),
            "ritmo_pct": st.column_config.ProgressColumn(
                "Ritmo a la fecha",
                min_value=0,
                max_value=120,
                format="%.1f %%",
            ),
            "brecha_esperada": st.column_config.NumberColumn("Brecha vs ritmo", format="$ %.0f"),
            "proyeccion_cierre": st.column_config.NumberColumn("Proyeccion", format="$ %.0f"),
            "brecha_objetivo": st.column_config.NumberColumn("Brecha objetivo", format="$ %.0f"),
            "venta_diaria_necesaria": st.column_config.NumberColumn("Diario necesario", format="$ %.0f"),
            "tiene_objetivo": None,
            "estado": "Estado",
        },
    )

st.divider()

ventas_dia = siscor_db.ventas_por_dia(desde_sql, hasta_sql, zonas_filtro)
ventas_mes = siscor_db.ventas_por_mes(desde_sql, hasta_sql, zonas_filtro)
ventas_zona = siscor_db.ventas_por_zona(desde_sql, hasta_sql, zonas_filtro)
top_clientes = siscor_db.top_clientes(desde_sql, hasta_sql, zonas_filtro)
top_productos = siscor_db.top_productos(desde_sql, hasta_sql, zonas_filtro)
clientes_recuperar = siscor_db.clientes_a_recuperar(
    mes_actual_desde.isoformat(),
    fecha_maxima.isoformat(),
    mes_anterior_desde.isoformat(),
    mes_anterior_hasta.isoformat(),
    zonas_filtro,
)
productos_impulsar = siscor_db.productos_a_impulsar(
    mes_actual_desde.isoformat(),
    fecha_maxima.isoformat(),
    mes_anterior_desde.isoformat(),
    mes_anterior_hasta.isoformat(),
    zonas_filtro,
)

radar_acciones = build_action_radar(desempeno_df, clientes_recuperar, productos_impulsar)
st.subheader("Radar de acciones")
if radar_acciones.empty:
    st.info("No hay alertas comerciales relevantes para este periodo.")
else:
    alta_prioridad = int((radar_acciones["prioridad"] == "Alta").sum())
    impacto_principal = radar_acciones["impacto_estimado"].max()
    zonas_priorizadas = radar_acciones.loc[radar_acciones["frente"] == "Zona", "zona"].nunique()
    a1, a2, a3 = st.columns(3)
    a1.metric("Acciones altas", number(alta_prioridad))
    a2.metric("Mayor oportunidad", money(impacto_principal))
    a3.metric("Zonas a empujar", number(zonas_priorizadas))

    plan_diario = build_daily_plan(radar_acciones)
    st.markdown("#### Plan diario recomendado")
    plan_cols = st.columns(len(plan_diario))
    for col, (_, row) in zip(plan_cols, plan_diario.iterrows()):
        with col:
            st.markdown(
                f"""
                <div class="dm-card">
                    <div class="dm-card-label">{row['orden']} - {row['prioridad']}</div>
                    <div class="dm-card-value">{row['titulo']}</div>
                    <div class="dm-card-note">{row['detalle']}</div>
                    <div class="dm-card-note">{row['accion']}</div>
                    <div class="dm-card-note">Impacto estimado: {money(row['impacto_estimado'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    resumen_ejecutivo = build_executive_brief(
        f"{mes_actual_desde.strftime('%d/%m/%Y')} al {fecha_maxima.strftime('%d/%m/%Y')}",
        total_ventas_mes,
        total_objetivo,
        ritmo_total,
        total_proyeccion - total_objetivo,
        venta_diaria_necesaria,
        plan_diario,
    )
    st.markdown("#### Resumen ejecutivo para compartir")
    st.text_area(
        "Texto sugerido",
        resumen_ejecutivo,
        height=210,
        label_visibility="collapsed",
    )

    st.dataframe(
        radar_acciones,
        use_container_width=True,
        hide_index=True,
        column_config={
            "prioridad": "Prioridad",
            "frente": "Frente",
            "zona": "Zona",
            "foco": "Foco",
            "impacto_estimado": st.column_config.NumberColumn("Impacto estimado", format="$ %.0f"),
            "accion": "Accion sugerida",
        },
    )

graf_1, graf_2 = st.columns([1.2, 1])
with graf_1:
    st.subheader("Ventas del periodo")
    serie = ventas_dia if periodo != "Rango" or len(ventas_mes) <= 2 else ventas_mes
    eje_x = "fecha" if "fecha" in serie.columns else "mes"
    fig = px.line(serie, x=eje_x, y="total", markers=True)
    fig.update_layout(xaxis_title="", yaxis_title="", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

with graf_2:
    st.subheader("Ventas por zona")
    fig = px.bar(ventas_zona.sort_values("total"), x="total", y="zona", orientation="h")
    fig.update_layout(xaxis_title="", yaxis_title="", height=460)
    st.plotly_chart(fig, use_container_width=True)

tab_clientes, tab_productos, tab_zonas = st.tabs(["Clientes", "Productos", "Zona"])

with tab_clientes:
    st.markdown("#### Clientes prioritarios para recuperar")
    st.dataframe(
        clientes_recuperar,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cliente": "Cliente",
            "zona": "Zona",
            "venta_mes": st.column_config.NumberColumn("Venta mes", format="$ %.0f"),
            "venta_mes_anterior": st.column_config.NumberColumn("Mes anterior", format="$ %.0f"),
            "variacion": st.column_config.NumberColumn("Variacion", format="$ %.0f"),
            "accion": "Accion sugerida",
        },
    )
    st.markdown("#### Principales clientes del periodo")
    st.dataframe(
        top_clientes,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cliente": "Cliente",
            "total": st.column_config.NumberColumn("Total", format="$ %.0f"),
            "comprobantes": st.column_config.NumberColumn("Comprobantes", format="%d"),
        },
    )

with tab_productos:
    st.markdown("#### Productos foco para impulsar")
    st.dataframe(
        productos_impulsar,
        use_container_width=True,
        hide_index=True,
        column_config={
            "producto": "Producto",
            "cantidad_mes": st.column_config.NumberColumn("Cantidad mes", format="%.2f"),
            "cantidad_mes_anterior": st.column_config.NumberColumn("Cantidad mes anterior", format="%.2f"),
            "venta_mes": st.column_config.NumberColumn("Venta mes", format="$ %.0f"),
            "venta_mes_anterior": st.column_config.NumberColumn("Mes anterior", format="$ %.0f"),
            "variacion": st.column_config.NumberColumn("Variacion", format="$ %.0f"),
            "accion": "Accion sugerida",
        },
    )
    st.markdown("#### Principales productos del periodo")
    st.dataframe(
        top_productos,
        use_container_width=True,
        hide_index=True,
        column_config={
            "producto": "Producto",
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
            "total": st.column_config.NumberColumn("Total", format="$ %.0f"),
        },
    )

with tab_zonas:
    st.dataframe(
        ventas_zona,
        use_container_width=True,
        hide_index=True,
        column_config={
            "zona": "Zona",
            "total": st.column_config.NumberColumn("Total", format="$ %.0f"),
            "comprobantes": st.column_config.NumberColumn("Comprobantes", format="%d"),
            "clientes": st.column_config.NumberColumn("Clientes", format="%d"),
        },
    )

st.subheader("Evolucion mensual")
st.dataframe(
    ventas_mes,
    use_container_width=True,
    hide_index=True,
    column_config={
        "mes": st.column_config.DateColumn("Mes", format="MM/YYYY"),
        "total": st.column_config.NumberColumn("Total", format="$ %.0f"),
        "comprobantes": st.column_config.NumberColumn("Comprobantes", format="%d"),
    },
)
