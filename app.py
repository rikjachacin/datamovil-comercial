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
        --dm-text: #182536;
        --dm-muted: #66758a;
        --dm-accent: #0f7b6c;
        --dm-accent-2: #1f5eff;
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
        background: #ffffff;
        border-right: 1px solid var(--dm-border);
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
    if current_user.is_admin:
        zona_seleccion = st.multiselect(
            "Zonas",
            options=zonas_disponibles,
            placeholder="Todas las zonas",
        )
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
