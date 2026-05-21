from __future__ import annotations

from datetime import timedelta
import html
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
        font-size: 23px;
        line-height: 1.18;
        white-space: normal;
        overflow-wrap: anywhere;
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

    .dm-table-wrap {
        overflow-x: auto;
        border: 1px solid var(--dm-border);
        border-radius: 8px;
        background: var(--dm-panel);
        padding: 8px;
        box-shadow: 0 8px 22px rgba(20, 36, 58, 0.05);
    }

    .dm-ranking-table {
        width: 100%;
        border-collapse: collapse;
        min-width: 1120px;
        font-size: 14px;
    }

    .dm-ranking-table th {
        text-align: left;
        color: var(--dm-muted);
        font-weight: 750;
        padding: 12px 10px;
        border-bottom: 1px solid var(--dm-border);
        background: #f8fafc;
    }

    .dm-ranking-table td {
        padding: 10px;
        border-bottom: 1px solid #e7edf5;
        color: var(--dm-text);
        vertical-align: middle;
    }

    .dm-ranking-table td.num {
        text-align: right;
        white-space: nowrap;
    }

    .dm-progress-cell {
        min-width: 150px;
    }

    .dm-progress-track {
        position: relative;
        height: 26px;
        border-radius: 7px;
        overflow: hidden;
        background: #eef2f7;
    }

    .dm-progress-fill {
        height: 100%;
        border-radius: 7px;
    }

    .dm-progress-label {
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        padding-right: 8px;
        font-weight: 800;
        color: #111827;
    }

    .dm-goal-board {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 12px;
    }

    .dm-goal-card {
        background: var(--dm-panel);
        border: 1px solid var(--dm-border);
        border-radius: 8px;
        padding: 14px 16px;
        box-shadow: 0 8px 22px rgba(20, 36, 58, 0.05);
    }

    .dm-goal-top {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: baseline;
        margin-bottom: 10px;
    }

    .dm-goal-zone {
        font-weight: 800;
        color: var(--dm-text);
    }

    .dm-goal-pct {
        font-size: 22px;
        font-weight: 850;
        white-space: nowrap;
    }

    .dm-goal-track {
        height: 13px;
        border-radius: 999px;
        overflow: hidden;
        margin-bottom: 10px;
    }

    .dm-goal-fill {
        height: 100%;
        border-radius: 999px;
    }

    .dm-goal-meta {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 6px 12px;
        color: var(--dm-muted);
        font-size: 13px;
    }

    .dm-goal-meta strong {
        display: block;
        color: var(--dm-text);
        font-size: 14px;
        margin-top: 2px;
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


def workdays(value: object) -> str:
    if pd.isna(value):
        return "0"
    numeric = float(value)
    if numeric.is_integer():
        return number(numeric)
    return f"{numeric:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def percent(value: object) -> str:
    if pd.isna(value):
        return "0,0 %"
    return f"{float(value) * 100:,.1f} %".replace(",", "X").replace(".", ",").replace("X", ".")


def percent_points(value: object) -> str:
    if pd.isna(value):
        return "0,0 %"
    return f"{float(value):,.1f} %".replace(",", "X").replace(".", ",").replace("X", ".")


def numeric_value(value: object) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return 0.0 if pd.isna(numeric) else float(numeric)


TELEMARKETING_ZONE_TOKENS = ("DAVID", "NOELIA", "MICAELA", "MACA", "MACARENA")


def is_telemarketing_zone(zona: object) -> bool:
    if isinstance(zona, (list, tuple, set)):
        return any(is_telemarketing_zone(value) for value in zona)
    zona_text = str(zona).upper()
    return any(token in zona_text for token in TELEMARKETING_ZONE_TOKENS)


def adapt_action_for_zone(action: object, zona: object) -> str:
    action_text = str(action)
    if not is_telemarketing_zone(zona):
        return action_text
    return (
        action_text.replace("Recuperar visita", "Recuperar contacto")
        .replace("visitas", "contactos")
        .replace("visita", "llamada")
        .replace("Acompanamiento diario", "Seguimiento diario")
        .replace("Impulsar en contactos y reposicion", "Impulsar por llamada y WhatsApp")
    )


def adapt_actions_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "accion" not in df.columns or "zona" not in df.columns:
        return df
    out = df.copy()
    out["accion"] = out.apply(lambda row: adapt_action_for_zone(row["accion"], row["zona"]), axis=1)
    return out


def progress_colors(value: object) -> tuple[str, str]:
    pct = min(max(numeric_value(value), 0), 100)
    if pct < 70:
        return "#ef4444", "#fee2e2"
    elif pct < 80:
        return "#f59e0b", "#fef3c7"
    return "#16a34a", "#dcfce7"


def progress_bar_html(value: object) -> str:
    pct = min(max(numeric_value(value), 0), 120)
    fill_pct = min(pct, 100)
    color, bg = progress_colors(pct)
    return (
        f'<div class="dm-progress-cell"><div class="dm-progress-track" style="background:{bg};">'
        f'<div class="dm-progress-fill" style="width:{fill_pct:.1f}%; background:{color};"></div>'
        f'<div class="dm-progress-label">{percent_points(pct)}</div>'
        "</div></div>"
    )


def render_ranking_table(df: pd.DataFrame) -> str:
    headers = [
        "Zona",
        "Ventas mes",
        "Objetivo",
        "Cumplimiento",
        "Ritmo a la fecha",
        "Proyeccion",
        "Brecha objetivo",
        "Diario necesario",
        "Brecha vs ritmo",
        "Estado",
    ]
    rows = []
    for _, row in df.iterrows():
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['zona']))}</td>"
            f"<td class='num'>{money(row['ventas_mes'])}</td>"
            f"<td class='num'>{money(row['objetivo'])}</td>"
            f"<td>{progress_bar_html(row['cumplimiento_pct'])}</td>"
            f"<td>{progress_bar_html(row['ritmo_pct'])}</td>"
            f"<td class='num'>{money(row['proyeccion_cierre'])}</td>"
            f"<td class='num'>{money(row['brecha_objetivo'])}</td>"
            f"<td class='num'>{money(row['venta_diaria_necesaria'])}</td>"
            f"<td class='num'>{money(row['brecha_esperada'])}</td>"
            f"<td>{html.escape(str(row['estado']))}</td>"
            "</tr>"
        )
    header_html = "".join(f"<th>{header}</th>" for header in headers)
    body_html = "".join(rows)
    return f'<div class="dm-table-wrap"><table class="dm-ranking-table"><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table></div>'


def render_goal_board(df: pd.DataFrame) -> str:
    cards = []
    for _, row in df.iterrows():
        pct = min(max(numeric_value(row["cumplimiento_pct"]), 0), 120)
        fill_pct = min(pct, 100)
        color, bg = progress_colors(pct)
        zone = html.escape(str(row["zona"]))
        status = html.escape(str(row["estado"]))
        cards.append(
            "<div class='dm-goal-card'>"
            "<div class='dm-goal-top'>"
            f"<div class='dm-goal-zone'>{zone}</div>"
            f"<div class='dm-goal-pct' style='color:{color};'>{percent_points(pct)}</div>"
            "</div>"
            f"<div class='dm-goal-track' style='background:{bg};'>"
            f"<div class='dm-goal-fill' style='width:{fill_pct:.1f}%; background:{color};'></div>"
            "</div>"
            "<div class='dm-goal-meta'>"
            f"<div>Vendido<strong>{money(row['ventas_mes'])}</strong></div>"
            f"<div>Objetivo<strong>{money(row['objetivo'])}</strong></div>"
            f"<div>Diario necesario<strong>{money(row['venta_diaria_necesaria'])}</strong></div>"
            f"<div>Estado<strong>{status}</strong></div>"
            "</div>"
            "</div>"
        )
    return "<div class='dm-goal-board'>" + "".join(cards) + "</div>"


def seller_action_message(
    performance_row: pd.Series | None,
    clients: pd.DataFrame,
    products: pd.DataFrame,
    zonas: tuple[str, ...],
) -> str:
    if performance_row is None:
        return "No hay objetivo asignado para esta zona. Revisar configuracion antes de evaluar desempeno."

    is_telemarketing = is_telemarketing_zone(zonas)
    status = str(performance_row["estado"])
    if is_telemarketing and status == "En ritmo":
        base = "Vas en ritmo. Mantene frecuencia de contacto, confirma reposicion y cuida clientes activos."
    elif is_telemarketing and status == "Cerca":
        base = "Estas cerca del ritmo. Un bloque corto de llamadas puede recuperar la brecha de este mes."
    elif is_telemarketing:
        base = "Necesitas recuperar ritmo. Prioriza llamadas a clientes caidos y productos con baja frente al mes anterior."
    elif status == "En ritmo":
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


def client_strategy_message(cliente: str, resumen: pd.Series, caidos: pd.DataFrame, zonas: tuple[str, ...]) -> str:
    venta_mes = numeric_value(resumen.get("venta_mes"))
    venta_anterior = numeric_value(resumen.get("venta_mes_anterior"))
    variacion = venta_mes - venta_anterior
    is_telemarketing = is_telemarketing_zone(zonas)
    ultima_compra = resumen.get("ultima_compra")
    tiene_historial = not pd.isna(ultima_compra)

    if venta_anterior <= 0 and venta_mes > 0:
        message = f"{cliente} aparece activo este mes. Conviene sostener frecuencia y revisar productos complementarios."
    elif venta_mes <= 0 and venta_anterior > 0:
        if is_telemarketing:
            message = f"{cliente} compro el mes anterior y este mes no registra compra. Prioridad alta para llamada o WhatsApp."
        else:
            message = f"{cliente} compro el mes anterior y este mes no registra compra. Prioridad alta para contacto o visita."
    elif venta_mes <= 0 and venta_anterior <= 0 and tiene_historial:
        if is_telemarketing:
            message = f"{cliente} no registra compra reciente. Ultima compra: {ultima_compra}. Prioridad para reactivar por llamada o WhatsApp."
        else:
            message = f"{cliente} no registra compra reciente. Ultima compra: {ultima_compra}. Prioridad para reactivar contacto o visita."
    elif variacion < 0:
        if is_telemarketing:
            message = f"{cliente} bajo {money(abs(variacion))} frente al mes anterior. Enfocar el contacto en recuperar rotacion."
        else:
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
                    "accion": adapt_action_for_zone(
                        "Acompanamiento diario y foco en clientes de mayor potencial",
                        row["zona"],
                    ),
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
                    "accion": adapt_action_for_zone(row.get("accion", "Contactar y recuperar compra"), row.get("zona")),
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
                    "accion": "Impulsar en gestion comercial y reposicion",
                }
            )

    if not rows:
        return pd.DataFrame(columns=["prioridad", "frente", "zona", "foco", "accion"])

    radar = pd.DataFrame(rows)
    priority_order = {"Alta": 0, "Media": 1, "Baja": 2}
    radar["orden"] = radar["prioridad"].map(priority_order).fillna(9)
    radar = radar.sort_values(["orden", "impacto_estimado"], ascending=[True, False]).head(limit)
    return radar.drop(columns=["orden", "impacto_estimado"])


def build_daily_plan(radar: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    if radar.empty:
        return pd.DataFrame(columns=["orden", "prioridad", "titulo", "detalle", "accion"])

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
                f"{row['accion']}."
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
periodo_dias = (fecha_hasta - fecha_desde).days + 1
comparacion_hasta = fecha_desde - timedelta(days=1)
comparacion_desde = comparacion_hasta - timedelta(days=periodo_dias - 1)
comparacion_desde_sql = comparacion_desde.isoformat()
comparacion_hasta_sql = comparacion_hasta.isoformat()

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
    ventas_periodo_vendedor = siscor_db.ventas_por_zona(
        desde_sql,
        hasta_sql,
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
        desde_sql,
        hasta_sql,
        comparacion_desde_sql,
        comparacion_hasta_sql,
        zonas_filtro,
        limite=5,
    )
    clientes_vendedor = adapt_actions_dataframe(clientes_vendedor)
    productos_vendedor = siscor_db.productos_a_impulsar(
        desde_sql,
        hasta_sql,
        comparacion_desde_sql,
        comparacion_hasta_sql,
        zonas_filtro,
        limite=5,
    )
    top_clientes_vendedor = siscor_db.top_clientes(
        desde_sql,
        hasta_sql,
        zonas_filtro,
        limite=8,
    )
    clientes_catalogo_vendedor = siscor_db.clientes_busqueda(zonas_filtro)

    st.subheader("Mi avance del mes" if periodo == "Mes en curso" else "Mi avance del periodo")
    if vendedor_row is None:
        st.warning("Tu zona no tiene objetivo cargado para este mes.")
    else:
        if periodo == "Mes en curso":
            v1, v2, v3 = st.columns(3)
            v1.metric("Ventas mes", money(vendedor_row["ventas_mes"]))
            v2.metric("Objetivo", money(vendedor_row["objetivo"]))
            v3.metric("Cumplimiento", percent(vendedor_row["cumplimiento"]))

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Diario necesario", money(vendedor_row["venta_diaria_necesaria"]))
            r2.metric("Dias para vender", workdays(dias_restantes))
            r3.metric("Ritmo a la fecha", percent(vendedor_row["ritmo"]))
            r4.metric("Proyeccion cierre", money(vendedor_row["proyeccion_cierre"]))

            b1, _ = st.columns([1, 3])
            b1.metric("Brecha objetivo", money(vendedor_row["brecha_objetivo"]))
        else:
            ventas_periodo_total = (
                ventas_periodo_vendedor["total"].sum() if not ventas_periodo_vendedor.empty else 0
            )
            periodo_objetivo_desde = max(fecha_desde, mes_actual_desde)
            periodo_objetivo_hasta = min(fecha_hasta, fecha_maxima)
            dias_periodo_objetivo = objectives.business_days_between(
                periodo_objetivo_desde,
                periodo_objetivo_hasta,
            )
            dias_mes_objetivo = objectives.business_days_in_month(fecha_maxima)
            objetivo_periodo = (
                numeric_value(vendedor_row["objetivo"]) * dias_periodo_objetivo / dias_mes_objetivo
                if dias_mes_objetivo
                else 0
            )
            cumplimiento_periodo = (
                ventas_periodo_total / objetivo_periodo if objetivo_periodo else 0
            )
            brecha_periodo = ventas_periodo_total - objetivo_periodo

            v1, v2, v3, v4 = st.columns(4)
            v1.metric("Ventas periodo", money(ventas_periodo_total))
            v2.metric("Objetivo periodo", money(objetivo_periodo))
            v3.metric("Cumplimiento periodo", percent(cumplimiento_periodo))
            v4.metric("Dias periodo", workdays(dias_periodo_objetivo))

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Objetivo mensual", money(vendedor_row["objetivo"]))
            r2.metric("Diario necesario mes", money(vendedor_row["venta_diaria_necesaria"]))
            r3.metric("Ritmo mes", percent(vendedor_row["ritmo"]))
            r4.metric("Brecha periodo", money(brecha_periodo))
            st.caption(
                "El objetivo del periodo se calcula proporcionalmente sobre los dias comerciales del mes."
            )

    st.info(seller_action_message(vendedor_row, clientes_vendedor, productos_vendedor, zonas_filtro))

    seccion_vendedor = st.segmented_control(
        "Detalle vendedor",
        ["Plan de accion", "Clientes", "Productos"],
        default="Plan de accion",
        label_visibility="collapsed",
        key="detalle_vendedor",
    )
    if seccion_vendedor == "Plan de accion":
        st.markdown("#### Clientes a recuperar")
        st.dataframe(
            clientes_vendedor,
            use_container_width=True,
            hide_index=True,
            column_config={
                "cliente": "Cliente",
                "zona": "Zona",
                "venta_mes": st.column_config.NumberColumn("Venta periodo", format="$ %.0f"),
                "venta_mes_anterior": st.column_config.NumberColumn("Periodo anterior", format="$ %.0f"),
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
                "cantidad_mes": st.column_config.NumberColumn("Cantidad periodo", format="%.2f"),
                "cantidad_mes_anterior": st.column_config.NumberColumn("Cantidad anterior", format="%.2f"),
                "venta_mes": st.column_config.NumberColumn("Venta periodo", format="$ %.0f"),
                "venta_mes_anterior": st.column_config.NumberColumn("Periodo anterior", format="$ %.0f"),
                "variacion": st.column_config.NumberColumn("Variacion", format="$ %.0f"),
                "accion": "Accion sugerida",
            },
        )

    elif seccion_vendedor == "Clientes":
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

    else:
        st.dataframe(
            siscor_db.top_productos(
                desde_sql,
                hasta_sql,
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
                clientes_catalogo_vendedor.get("cliente", pd.Series(dtype=str)),
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
        st.info("No hay clientes disponibles para generar estrategia en esta zona.")

    if cliente_seleccionado:
        resumen_cliente, productos_cliente, caidos_cliente = siscor_db.estrategia_cliente(
            cliente_seleccionado,
            desde_sql,
            hasta_sql,
            comparacion_desde_sql,
            comparacion_hasta_sql,
            zonas_filtro,
        )
        resumen_row = resumen_cliente.iloc[0]
        venta_mes_cliente = numeric_value(resumen_row["venta_mes"])
        venta_anterior_cliente = numeric_value(resumen_row["venta_mes_anterior"])
        ultima_compra = resumen_row["ultima_compra"]
        ultima_compra_texto = "Sin compra" if pd.isna(ultima_compra) else str(ultima_compra)
        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Venta periodo", money(venta_mes_cliente))
        ec2.metric("Periodo anterior", money(venta_anterior_cliente))
        ec3.metric("Variacion", money(venta_mes_cliente - venta_anterior_cliente))
        ec4.metric("Ultima compra", ultima_compra_texto)
        st.info(client_strategy_message(cliente_seleccionado, resumen_row, caidos_cliente, zonas_filtro))

        credito_cliente = siscor_db.cliente_credito(cliente_seleccionado, zonas_filtro)
        if not credito_cliente.empty:
            credito_row = credito_cliente.iloc[0]
            st.markdown("#### Perfil de credito sugerido")
            dc1, dc2, dc3, dc4 = st.columns(4)
            dc1.metric("Dias deuda a la fecha", number(credito_row["dias_deuda"]))
            dc2.metric("Importe de deuda", money(credito_row["importe_deuda"]))
            dc3.metric("Dias credito sugerido", number(credito_row["dias_credito_sugerido"]))
            dc4.metric("Limite compra sugerido", money(credito_row["limite_compra_sugerido"]))
            st.caption(
                f"Segmento {credito_row['categoria_abc']} - "
                f"{credito_row['segmento_pago']}. {credito_row['recomendacion_credito']}"
            )

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
                    "venta_mes": st.column_config.NumberColumn("Venta periodo", format="$ %.0f"),
                    "venta_mes_anterior": st.column_config.NumberColumn("Periodo anterior", format="$ %.0f"),
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

mes_referencia = objectives.month_key(fecha_hasta)
mes_referencia_desde = pd.Timestamp(fecha_hasta).replace(day=1).date()
zonas_objetivo_periodo = tuple(
    objetivos_df.loc[objetivos_df["mes"] == mes_referencia, "zona"].dropna().astype(str)
)
zonas_objetivo_filtradas = tuple(
    zona for zona in zonas_objetivo_periodo if not zonas_filtro or zona in zonas_filtro
)
if not zonas_objetivo_filtradas:
    zonas_objetivo_filtradas = zonas_filtro or zonas_objetivo_periodo

if periodo == "Mes en curso":
    objetivo_desde = mes_referencia_desde
    objetivo_hasta = fecha_hasta
    objetivos_calculo = objetivos_df[
        (objetivos_df["mes"] == mes_referencia)
        & (objetivos_df["zona"].isin(zonas_objetivo_filtradas))
    ].copy()
    avance_objetivo = objectives.month_progress(fecha_hasta)
    dias_objetivo = objectives.remaining_days(fecha_hasta)
    dias_display_objetivo = dias_objetivo
    objetivo_titulo = "Objetivos y ritmo del mes"
    label_cumplimiento = "Cumplimiento mensual"
    label_ritmo_esperado = "Ritmo esperado"
    label_proyeccion = "Proyeccion de cierre"
    label_brecha = "Brecha proyectada"
    label_diario = "Venta diaria necesaria"
    label_dias = "Dias para vender"
else:
    objetivo_desde = fecha_desde
    objetivo_hasta = fecha_hasta
    periodo_objetivo_desde = max(fecha_desde, mes_referencia_desde)
    periodo_objetivo_hasta = fecha_hasta
    dias_periodo_objetivo = objectives.business_days_between(
        periodo_objetivo_desde,
        periodo_objetivo_hasta,
    )
    dias_mes_referencia = objectives.business_days_in_month(fecha_hasta)
    proporcion_objetivo = dias_periodo_objetivo / dias_mes_referencia if dias_mes_referencia else 0
    objetivos_calculo = objetivos_df[
        (objetivos_df["mes"] == mes_referencia)
        & (objetivos_df["zona"].isin(zonas_objetivo_filtradas))
    ].copy()
    objetivos_calculo.loc[
        objetivos_calculo["mes"] == mes_referencia,
        "objetivo",
    ] = objetivos_calculo.loc[
        objetivos_calculo["mes"] == mes_referencia,
        "objetivo",
    ] * proporcion_objetivo
    avance_objetivo = 1.0
    dias_objetivo = 1.0
    dias_display_objetivo = dias_periodo_objetivo
    objetivo_titulo = "Objetivos del periodo"
    label_cumplimiento = "Cumplimiento periodo"
    label_ritmo_esperado = "Peso del periodo"
    label_proyeccion = "Ventas del periodo"
    label_brecha = "Brecha periodo"
    label_diario = "Falta periodo"
    label_dias = "Dias periodo"

ventas_objetivo = siscor_db.ventas_por_zona(
    objetivo_desde.isoformat(),
    objetivo_hasta.isoformat(),
    zonas_objetivo_filtradas,
)

st.subheader(objetivo_titulo)
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
        objetivos_calculo,
        mes_referencia,
        avance_objetivo,
        dias_objetivo,
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
    c1.metric(label_cumplimiento, percent(cumplimiento_total))
    c2.metric(label_ritmo_esperado, percent(avance_objetivo if periodo == "Mes en curso" else proporcion_objetivo))
    c3.metric("Ritmo del equipo", percent(ritmo_total))
    c4.metric("Zonas en ritmo", f"{zonas_en_ritmo}/{len(desempeno_con_objetivo)}")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric(label_proyeccion, money(total_proyeccion))
    p2.metric(label_brecha, money(total_proyeccion - total_objetivo))
    p3.metric(label_diario, money(venta_diaria_necesaria))
    p4.metric(label_dias, workdays(dias_display_objetivo))

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
    st.markdown("#### Cumplimiento por zona")
    st.markdown(render_goal_board(ranking_df), unsafe_allow_html=True)

st.divider()

ventas_dia = siscor_db.ventas_por_dia(desde_sql, hasta_sql, zonas_filtro)
ventas_mes = siscor_db.ventas_por_mes(desde_sql, hasta_sql, zonas_filtro)
ventas_zona = siscor_db.ventas_por_zona(desde_sql, hasta_sql, zonas_filtro)
top_clientes = siscor_db.top_clientes(desde_sql, hasta_sql, zonas_filtro)
top_productos = siscor_db.top_productos(desde_sql, hasta_sql, zonas_filtro)
clientes_recuperar = siscor_db.clientes_a_recuperar(
    desde_sql,
    hasta_sql,
    comparacion_desde_sql,
    comparacion_hasta_sql,
    zonas_filtro,
)
clientes_recuperar = adapt_actions_dataframe(clientes_recuperar)
productos_impulsar = siscor_db.productos_a_impulsar(
    desde_sql,
    hasta_sql,
    comparacion_desde_sql,
    comparacion_hasta_sql,
    zonas_filtro,
)

radar_acciones = build_action_radar(desempeno_df, clientes_recuperar, productos_impulsar)
st.subheader("Radar de acciones")
if radar_acciones.empty:
    st.info("No hay alertas comerciales relevantes para este periodo.")
else:
    alta_prioridad = int((radar_acciones["prioridad"] == "Alta").sum())
    zonas_priorizadas = radar_acciones.loc[radar_acciones["frente"] == "Zona", "zona"].nunique()
    clientes_priorizados = radar_acciones.loc[radar_acciones["frente"] == "Cliente", "foco"].nunique()
    a1, a2, a3 = st.columns(3)
    a1.metric("Acciones altas", number(alta_prioridad))
    a2.metric("Clientes a recuperar", number(clientes_priorizados))
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
                </div>
                """,
                unsafe_allow_html=True,
            )

    resumen_ejecutivo = build_executive_brief(
        f"{fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')}",
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
            "venta_mes": st.column_config.NumberColumn("Venta periodo", format="$ %.0f"),
            "venta_mes_anterior": st.column_config.NumberColumn("Periodo anterior", format="$ %.0f"),
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
            "cantidad_mes": st.column_config.NumberColumn("Cantidad periodo", format="%.2f"),
            "cantidad_mes_anterior": st.column_config.NumberColumn("Cantidad periodo anterior", format="%.2f"),
            "venta_mes": st.column_config.NumberColumn("Venta periodo", format="$ %.0f"),
            "venta_mes_anterior": st.column_config.NumberColumn("Periodo anterior", format="$ %.0f"),
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
