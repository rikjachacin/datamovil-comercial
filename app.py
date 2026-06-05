from __future__ import annotations

import base64
from datetime import date, timedelta
import html
from pathlib import Path
import traceback

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from src import auth
from src import anura_api
from src import objectives
from src import persat_api
from src import siscor_db


APP_NAME = "Bruncas Comercial"
APP_BUILD = "2026-05-22.1235"
LOGO_PATH = Path("assets/bruncas_logo.png")


st.set_page_config(
    page_title=APP_NAME,
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
        --dm-brand-gold: #d9b51f;
        --dm-brand-purple: #8d168f;
        --dm-sidebar: #f8fbfd;
    }

    .stApp {
        background:
            radial-gradient(circle at 15% 0%, rgba(217, 181, 31, 0.10) 0, transparent 260px),
            radial-gradient(circle at 85% 4%, rgba(141, 22, 143, 0.08) 0, transparent 280px),
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
            linear-gradient(180deg, #ffffff 0%, var(--dm-sidebar) 60%, #f5f8ec 100%);
        border-right: 1px solid var(--dm-border);
        box-shadow: 8px 0 28px rgba(20, 36, 58, 0.06);
    }

    [data-testid="stSidebar"]::before {
        content: "";
        display: block;
        height: 4px;
        margin: -1.3rem -1rem 1.1rem;
        background: linear-gradient(90deg, var(--dm-brand-purple), var(--dm-brand-gold), var(--dm-accent));
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
        background: linear-gradient(180deg, var(--dm-brand-purple), var(--dm-brand-gold));
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
        display: flex;
        align-items: center;
        gap: 22px;
        border: 1px solid var(--dm-border);
        border-top: 4px solid var(--dm-brand-gold);
        background:
            linear-gradient(135deg, #ffffff 0%, #eef7f5 48%, #eef3ff 100%);
        border-radius: 8px;
        padding: 20px 24px;
        margin-bottom: 18px;
        box-shadow: 0 14px 34px rgba(25, 40, 64, 0.09);
    }

    .dm-logo {
        width: 178px;
        max-width: 34vw;
        height: auto;
        object-fit: contain;
        flex: 0 0 auto;
    }

    .dm-header-text {
        min-width: 0;
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

    @media (max-width: 720px) {
        .dm-header {
            align-items: flex-start;
            flex-direction: column;
            gap: 12px;
            padding: 18px;
        }

        .dm-logo {
            width: 150px;
            max-width: 70vw;
        }

        .dm-title {
            font-size: 29px;
        }
    }

    [data-testid="stMetric"] {
        background: var(--dm-panel);
        border: 1px solid var(--dm-border);
        border-top: 3px solid rgba(217, 181, 31, 0.72);
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

    .dm-metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(185px, 1fr));
        gap: 14px;
        margin: 0 0 14px;
    }

    .dm-compact-metric {
        min-width: 0;
        background: var(--dm-panel);
        border: 1px solid var(--dm-border);
        border-top: 3px solid rgba(15, 123, 108, 0.50);
        border-radius: 8px;
        padding: 15px 17px;
        box-shadow: 0 8px 22px rgba(20, 36, 58, 0.06);
    }

    .dm-compact-label {
        color: var(--dm-muted);
        font-size: 14px;
        font-weight: 650;
        line-height: 1.25;
        margin-bottom: 8px;
    }

    .dm-compact-value {
        color: var(--dm-text);
        font-size: 24px;
        font-weight: 520;
        line-height: 1.14;
        overflow-wrap: anywhere;
    }

    .dm-module-heading {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 26px 0 14px;
        padding: 12px 14px;
        border: 1px solid var(--module-border, var(--dm-border));
        border-left: 6px solid var(--module-accent, var(--dm-accent));
        border-radius: 8px;
        background: var(--module-bg, #ffffff);
        box-shadow: 0 8px 20px rgba(20, 36, 58, 0.04);
    }

    h1, h2, h3 {
        letter-spacing: 0;
    }

    div[data-testid="stVerticalBlock"] > div:has(> hr) {
        margin: 0.8rem 0;
    }

    .dm-module-icon {
        width: 30px;
        height: 30px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
        background: var(--module-accent, var(--dm-accent));
        color: #ffffff;
        font-size: 16px;
        font-weight: 800;
        flex: 0 0 auto;
    }

    .dm-module-title {
        color: var(--dm-text);
        font-size: 22px;
        font-weight: 800;
        line-height: 1.15;
    }

    .dm-module-subtitle {
        color: var(--dm-muted);
        font-size: 13px;
        margin-top: 3px;
    }

    .dm-module-sales {
        --module-accent: #0f766e;
        --module-bg: #ecfdf5;
        --module-border: #b7eadb;
    }

    .dm-module-action {
        --module-accent: #d49a00;
        --module-bg: #fff8e6;
        --module-border: #f2d88a;
    }

    .dm-module-detail {
        --module-accent: #2563eb;
        --module-bg: #eff6ff;
        --module-border: #bfdbfe;
    }

    .dm-module-strategy {
        --module-accent: #7c3aed;
        --module-bg: #f5f3ff;
        --module-border: #ddd6fe;
    }

    .dm-module-credit {
        --module-accent: #15803d;
        --module-bg: #f0fdf4;
        --module-border: #bbf7d0;
    }

    .dm-module-products {
        --module-accent: #dc2626;
        --module-bg: #fff1f2;
        --module-border: #fecdd3;
    }

    @media (max-width: 720px) {
        .dm-metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-bottom: 12px;
        }

        .dm-compact-metric {
            min-height: 112px;
            padding: 12px 13px;
        }

        .dm-compact-label {
            font-size: 12.5px;
            margin-bottom: 7px;
        }

        .dm-compact-value {
            font-size: 19px;
        }

        .dm-module-heading {
            margin: 20px 0 12px;
            padding: 10px 11px;
            gap: 8px;
        }

        .dm-module-icon {
            width: 26px;
            height: 26px;
            font-size: 14px;
        }

        .dm-module-title {
            font-size: 19px;
        }

        .dm-module-subtitle {
            font-size: 12px;
        }

    }

    .stButton button {
        border-radius: 8px;
        border: 1px solid var(--dm-border-strong);
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        color: var(--dm-text);
        font-weight: 650;
        transition: all 120ms ease;
    }

    .stButton button:hover {
        border-color: var(--dm-accent);
        color: var(--dm-accent);
        box-shadow: 0 8px 18px rgba(15, 123, 108, 0.14);
        transform: translateY(-1px);
    }

    .dm-sidebar-nav {
        display: grid;
        gap: 8px;
        margin: 4px 0 2px;
    }

    .dm-sidebar-nav a {
        display: block;
        width: 100%;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--nav-border);
        background: linear-gradient(180deg, var(--nav-bg) 0%, var(--nav-bg-2) 100%);
        color: #182536;
        font-weight: 750;
        text-decoration: none;
        box-shadow: 0 6px 16px rgba(20, 36, 58, 0.06);
    }

    .dm-sidebar-nav a:hover {
        color: #182536;
        text-decoration: none;
        transform: translateY(-1px);
        box-shadow: 0 9px 20px rgba(20, 36, 58, 0.10);
    }

    .dm-sidebar-nav a.active {
        border-width: 2px;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.65), 0 9px 20px rgba(20, 36, 58, 0.10);
    }

    .dm-nav-panel {
        --nav-bg: #fff8cf;
        --nav-bg-2: #ffef8f;
        --nav-border: #e3c23a;
    }

    .dm-nav-persat {
        --nav-bg: #fff0dd;
        --nav-bg-2: #ffc680;
        --nav-border: #f28c28;
    }

    .dm-nav-anura {
        --nav-bg: #e9f9ee;
        --nav-bg-2: #a9e8bb;
        --nav-border: #22a35a;
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
        border-top: 3px solid rgba(141, 22, 143, 0.22);
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

    .dm-decision-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 12px 0 18px;
    }

    .dm-decision-card {
        background: var(--dm-panel);
        border: 1px solid var(--dm-border);
        border-left: 5px solid var(--decision-accent, var(--dm-accent));
        border-radius: 8px;
        padding: 15px 16px;
        box-shadow: 0 8px 22px rgba(20, 36, 58, 0.06);
        min-height: 150px;
    }

    .dm-decision-label {
        color: var(--dm-muted);
        font-size: 12px;
        font-weight: 800;
        text-transform: uppercase;
        margin-bottom: 8px;
    }

    .dm-decision-title {
        color: var(--dm-text);
        font-size: 18px;
        font-weight: 850;
        line-height: 1.2;
        margin-bottom: 8px;
    }

    .dm-decision-note {
        color: var(--dm-muted);
        font-size: 13px;
        line-height: 1.35;
    }

    @media (max-width: 900px) {
        .dm-decision-grid {
            grid-template-columns: 1fr;
        }
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


def render_metric_grid(items: list[tuple[str, str]]) -> str:
    cards = []
    for label, value in items:
        cards.append(
            "<div class='dm-compact-metric'>"
            f"<div class='dm-compact-label'>{html.escape(label)}</div>"
            f"<div class='dm-compact-value'>{html.escape(value)}</div>"
            "</div>"
        )
    return "<div class='dm-metric-grid'>" + "".join(cards) + "</div>"


def render_module_heading(title: str, subtitle: str = "", kind: str = "sales", icon: str = "") -> str:
    subtitle_html = f"<div class='dm-module-subtitle'>{html.escape(subtitle)}</div>" if subtitle else ""
    icon_html = f"<div class='dm-module-icon'>{html.escape(icon)}</div>" if icon else ""
    return (
        f"<div class='dm-module-heading dm-module-{html.escape(kind)}'>"
        f"{icon_html}"
        "<div>"
        f"<div class='dm-module-title'>{html.escape(title)}</div>"
        f"{subtitle_html}"
        "</div>"
        "</div>"
    )


def seller_action_message(
    performance_row: pd.Series | None,
    clients: pd.DataFrame,
    products: pd.DataFrame,
    zonas: tuple[str, ...],
    active_clients: pd.DataFrame | None = None,
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

    client_names: list[str] = []
    for source in (clients, active_clients):
        if source is None or source.empty or "cliente" not in source.columns:
            continue
        for value in source["cliente"].dropna().astype(str):
            clean_value = value.strip()
            if clean_value and clean_value not in client_names:
                client_names.append(clean_value)
            if len(client_names) >= 5:
                break
        if len(client_names) >= 5:
            break

    if client_names:
        base += " Clientes sugeridos para revisar: " + "; ".join(client_names[:5]) + "."
    if not products.empty:
        base += f" Producto foco: {products.iloc[0]['producto']}."
    return base


def show_persat_activity(
    fecha_desde_sql: str,
    fecha_hasta_sql: str,
    zonas: tuple[str, ...],
    title: str = "Actividad Persat",
) -> None:
    st.markdown(
        render_module_heading(
            title,
            "Visitas registradas por GPS y cruce contra ventas del periodo",
            "activity",
            "V",
        ),
        unsafe_allow_html=True,
    )

    result = persat_api.activity(fecha_desde_sql, fecha_hasta_sql, zonas)
    if not result.enabled:
        st.warning(result.message)
        return

    if result.visits.empty:
        st.info(result.message)
        return

    sold_clients = siscor_db.clientes_vendidos(fecha_desde_sql, fecha_hasta_sql, zonas)
    summary = persat_api.summarize(result.visits, sold_clients)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Visitas", number(summary["visitas"]))
    c2.metric("Clientes visitados", number(summary["clientes_visitados"]))
    c3.metric("Visitados con venta", number(summary["visitados_con_venta"]))
    c4.metric("Visitados sin venta", number(summary["visitados_sin_venta"]))

    detail = result.visits.copy()
    sold_ids = set(sold_clients.get("id_cliente", pd.Series(dtype=str)).dropna().astype(str).str.strip())
    detail["venta_periodo"] = detail["id_cliente"].astype(str).str.strip().isin(sold_ids).map(
        {True: "Con venta", False: "Sin venta"}
    )
    detail["fecha_hora"] = pd.to_datetime(detail["fecha_hora"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
    detail["duracion_min"] = detail["duracion_min"].round(1)
    st.dataframe(
        detail.loc[:, ["fecha_hora", "vendedor", "cliente", "duracion_min", "venta_periodo"]].head(40),
        use_container_width=True,
        hide_index=True,
        column_config={
            "fecha_hora": "Fecha y hora",
            "vendedor": "Vendedor",
            "cliente": "Cliente",
            "duracion_min": st.column_config.NumberColumn("Minutos", format="%.1f"),
            "venta_periodo": "Venta",
        },
    )


def show_anura_activity(
    fecha_desde_sql: str,
    fecha_hasta_sql: str,
    zonas: tuple[str, ...],
    title: str = "Actividad Anura",
) -> None:
    st.markdown(
        render_module_heading(
            title,
            "Llamadas de telemarketing y cruce contra ventas del periodo",
            "calls",
            "T",
        ),
        unsafe_allow_html=True,
    )

    if zonas and not any(str(zone).strip().upper() in anura_api.TELEMARKETING_ACCOUNTS for zone in zonas):
        st.info("Anura aplica a zonas de telemarketing: David, Noelia, Micaela y Maca Protto.")
        return

    result = anura_api.calls(fecha_desde_sql, fecha_hasta_sql, zonas)
    if not result.enabled:
        st.warning(result.message)
        return

    if result.calls.empty:
        st.info(result.message)
        return

    sold_clients = siscor_db.clientes_vendidos(fecha_desde_sql, fecha_hasta_sql, zonas)
    summary, detail = anura_api.summarize(result.calls, sold_clients)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Llamadas", number(summary["llamadas"]))
    c2.metric("Contestadas", number(summary["contestadas"]))
    c3.metric("No efectivas", number(summary["no_efectivas"]))
    c4.metric("Minutos hablados", number(round(summary["minutos_hablados"], 1)))

    c5, c6 = st.columns(2)
    c5.metric("Clientes llamados", number(summary["clientes_llamados"]))
    c6.metric("Llamados con venta", number(summary["llamados_con_venta"]))

    table = detail.copy()
    table["fecha_hora"] = pd.to_datetime(table["fecha_hora"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
    table["duracion_min"] = (pd.to_numeric(table["duracion_seg"], errors="coerce").fillna(0) / 60).round(1)
    st.dataframe(
        table.loc[:, ["fecha_hora", "telemarketer", "cliente", "telefono", "estado", "duracion_min", "venta_periodo"]]
        .head(50),
        use_container_width=True,
        hide_index=True,
        column_config={
            "fecha_hora": "Fecha y hora",
            "telemarketer": "Telemarketer",
            "cliente": "Cliente / destino",
            "telefono": "Telefono",
            "estado": "Estado",
            "duracion_min": st.column_config.NumberColumn("Minutos", format="%.1f"),
            "venta_periodo": "Venta",
        },
    )


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


def render_decision_room(
    total_sales: float,
    total_goal: float,
    team_pace: float,
    projected_gap: float,
    daily_needed: float,
    insights: dict[str, object],
    plan: pd.DataFrame,
) -> str:
    if not total_goal:
        cards = [
            ("Diagnostico", "Sin objetivo cargado", "No se puede evaluar ritmo ni brecha sin meta mensual.", "#64748b"),
            ("Decision", "Cargar objetivos", "Primero hay que validar objetivos por zona para leer el mes.", "#64748b"),
            ("Foco de hoy", "Sin foco automatico", "La app necesita objetivo y ventas para priorizar.", "#64748b"),
            ("Riesgo", "Sin lectura", "No hay base suficiente para medir riesgo comercial.", "#64748b"),
        ]
    else:
        if team_pace >= 1:
            status = "Equipo en ritmo"
            status_note = f"Ventas {money(total_sales)} contra objetivo {money(total_goal)}."
            decision = "Sostener y proteger"
            decision_note = "Mantener frecuencia comercial y cuidar reposicion de clientes activos."
            accent = "#16a34a"
        elif team_pace >= 0.85:
            status = "Riesgo moderado"
            status_note = f"Brecha proyectada {money(projected_gap)} si no se corrige el ritmo."
            decision = "Concentrar apoyo"
            decision_note = "Enfocar seguimiento diario en las zonas cerca del ritmo para cerrar la brecha."
            accent = "#f59e0b"
        else:
            status = "Fuera de ritmo"
            status_note = f"Venta diaria necesaria: {money(daily_needed)} para llegar al objetivo."
            decision = "Intervenir hoy"
            decision_note = "Priorizar zonas atrasadas, clientes caidos y productos con caida de rotacion."
            accent = "#ef4444"

        if not plan.empty:
            first = plan.iloc[0]
            focus = str(first["titulo"])
            focus_note = f"{first['detalle']} - {first['accion']}."
        else:
            focus = "Sin alerta critica"
            focus_note = "No hay acciones prioritarias detectadas para este periodo."

        risk = insights.get("risk")
        if risk is not None:
            risk_title = str(risk["zona"])
            risk_note = f"Mayor brecha contra ritmo esperado: {money(risk['brecha_esperada'])}."
        else:
            risk_title = "Sin riesgo marcado"
            risk_note = "No hay zonas con objetivo suficiente para calcular riesgo."

        cards = [
            ("Diagnostico", status, status_note, accent),
            ("Decision", decision, decision_note, accent),
            ("Foco de hoy", focus, focus_note, "#2563eb"),
            ("Riesgo principal", risk_title, risk_note, "#7c3aed"),
        ]

    card_html = []
    for label, title, note, color in cards:
        card_html.append(
            f'<div class="dm-decision-card" style="--decision-accent:{html.escape(color)};">'
            f'<div class="dm-decision-label">{html.escape(label)}</div>'
            f'<div class="dm-decision-title">{html.escape(title)}</div>'
            f'<div class="dm-decision-note">{html.escape(note)}</div>'
            "</div>"
        )
    return '<div class="dm-decision-grid">' + "".join(card_html) + "</div>"


def logo_data_uri() -> str:
    if not LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def app_header_html(subtitle: str) -> str:
    logo_src = logo_data_uri()
    logo_html = f'<img class="dm-logo" src="{logo_src}" alt="Bruncas">' if logo_src else ""
    return f"""
        <div class="dm-header">
            {logo_html}
            <div class="dm-header-text">
                <div class="dm-title">{APP_NAME}</div>
                <div class="dm-subtitle">{subtitle}</div>
            </div>
        </div>
    """


def set_session_cookie(token: str) -> None:
    st.query_params[auth.SESSION_QUERY_PARAM] = token
    components.html(
        f"""
        <script>
        document.cookie = "{auth.SESSION_COOKIE_NAME}={token}; max-age={auth.SESSION_MAX_AGE_SECONDS}; path=/; SameSite=Lax";
        </script>
        """,
        height=0,
    )


def clear_session_cookie() -> None:
    if auth.SESSION_QUERY_PARAM in st.query_params:
        del st.query_params[auth.SESSION_QUERY_PARAM]
    components.html(
        f"""
        <script>
        document.cookie = "{auth.SESSION_COOKIE_NAME}=; max-age=0; path=/; SameSite=Lax";
        </script>
        """,
        height=0,
    )


def login_screen() -> None:
    st.markdown(
        app_header_html("Ingreso privado al panel comercial"),
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
            blocked_seconds = auth.login_block_seconds(username)
            if blocked_seconds:
                st.error(f"Demasiados intentos fallidos. Proba de nuevo en {blocked_seconds // 60 + 1} minutos.")
                return

            user = auth.authenticate(username, password)
            if user is None:
                st.error("Usuario o contrasena incorrectos.")
            else:
                st.session_state["user"] = user
                token = auth.create_session_token(user)
                set_session_cookie(token)
                st.rerun()


if "user" not in st.session_state:
    session_token = st.context.cookies.get(auth.SESSION_COOKIE_NAME) or st.query_params.get(auth.SESSION_QUERY_PARAM)
    session_user = auth.user_from_session_token(session_token)
    if session_user is not None:
        st.session_state["user"] = session_user
        set_session_cookie(session_token)
        st.rerun()
    else:
        login_screen()
        st.stop()

current_user: auth.User = st.session_state["user"]

st.markdown(
    app_header_html("Panel comercial conectado a datos reales de SisCor"),
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Usuario")
    st.write(current_user.name)
    st.caption("Administrador" if current_user.is_admin else "Zona asignada")
    if st.button("Cerrar sesion", use_container_width=True):
        clear_session_cookie()
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

        if st.button("Actualizar datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

try:
    limites = siscor_db.month_options().iloc[0]
    fecha_datos_maxima = pd.to_datetime(limites["fecha_maxima"]).date()
    fecha_maxima = max(fecha_datos_maxima, date.today())
    fecha_minima = pd.to_datetime(limites["fecha_minima"]).date()
    fecha_hoy = min(max(date.today(), fecha_minima), fecha_maxima)
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
    st.subheader("Pantallas")
    pantalla_param = str(st.query_params.get("pantalla", "panel")).lower()
    pantalla_map = {
        "panel": "Panel comercial",
        "persat": "Historial Persat",
        "anura": "Historial Anura",
    }
    pantalla_activa = pantalla_map.get(pantalla_param, "Panel comercial")
    nav_items = [
        ("panel", "Panel comercial", "dm-nav-panel"),
        ("persat", "Historial Persat", "dm-nav-persat"),
        ("anura", "Historial Anura", "dm-nav-anura"),
    ]
    nav_html = ['<div class="dm-sidebar-nav">']
    for key, label, css_class in nav_items:
        active_class = " active" if pantalla_activa == label else ""
        nav_html.append(
            f'<a class="{css_class}{active_class}" href="?pantalla={key}">{html.escape(label)}</a>'
        )
    nav_html.append("</div>")
    st.markdown("".join(nav_html), unsafe_allow_html=True)

    st.divider()
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
        key="periodo_selector",
    )
    if st.session_state.get("_ultimo_periodo_selector") != periodo:
        if periodo == "Rango":
            st.session_state["fecha_desde_rango"] = fecha_hoy
            st.session_state["fecha_hasta_rango"] = fecha_hoy
        st.session_state["_ultimo_periodo_selector"] = periodo

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
            value=fecha_hoy,
            min_value=fecha_minima,
            max_value=fecha_maxima,
            key="fecha_desde_rango",
        )
        fecha_hasta = st.date_input(
            "Hasta",
            value=fecha_hoy,
            min_value=fecha_minima,
            max_value=fecha_maxima,
            key="fecha_hasta_rango",
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
if not current_user.is_admin and not zonas_filtro:
    st.error("Tu usuario no tiene permisos para consultar datos comerciales. Revisar zona asignada.")
    st.stop()

if current_user.is_admin and not zonas_filtro and zonas_objetivo:
    zonas_filtro = zonas_objetivo

if fecha_desde > fecha_hasta:
    st.warning("La fecha desde no puede ser mayor que la fecha hasta.")
    st.stop()

desde_sql = fecha_desde.isoformat()
hasta_sql = fecha_hasta.isoformat()

if pantalla_activa == "Historial Persat":
    show_persat_activity(desde_sql, hasta_sql, zonas_filtro, "Historial Persat")
    st.stop()

if pantalla_activa == "Historial Anura":
    show_anura_activity(desde_sql, hasta_sql, zonas_filtro, "Historial Anura")
    st.stop()

periodo_dias = (fecha_hasta - fecha_desde).days + 1
comparacion_hasta = fecha_desde - timedelta(days=1)
comparacion_desde = comparacion_hasta - timedelta(days=periodo_dias - 1)
comparacion_desde_sql = comparacion_desde.isoformat()
comparacion_hasta_sql = comparacion_hasta.isoformat()
accion_comparacion_desde = comparacion_desde
accion_comparacion_hasta = comparacion_hasta
accion_comparacion_label = "periodo anterior"
if periodo == "Mes en curso":
    accion_comparacion_desde = mes_anterior_desde
    accion_comparacion_hasta = mes_anterior_hasta
    accion_comparacion_label = "mes anterior"
historial_cliente_hasta = fecha_maxima
historial_cliente_desde = (
    pd.Timestamp(historial_cliente_hasta) - pd.DateOffset(years=2) + pd.Timedelta(days=1)
).date()
historial_cliente_anterior_hasta = historial_cliente_desde - timedelta(days=1)
historial_cliente_anterior_desde = (
    pd.Timestamp(historial_cliente_anterior_hasta) - pd.DateOffset(years=2) + pd.Timedelta(days=1)
).date()

cliente_comparacion_desde = comparacion_desde
cliente_comparacion_hasta = comparacion_hasta
cliente_comparacion_label = "Periodo anterior"
cliente_en_mes_actual = (
    fecha_desde.year == fecha_maxima.year
    and fecha_desde.month == fecha_maxima.month
    and fecha_hasta.year == fecha_maxima.year
    and fecha_hasta.month == fecha_maxima.month
)
if periodo == "Mes en curso" or cliente_en_mes_actual:
    cliente_comparacion_desde = mes_anterior_desde
    cliente_comparacion_hasta = mes_anterior_hasta
    cliente_comparacion_label = "Mes anterior"

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
        accion_comparacion_desde.isoformat(),
        accion_comparacion_hasta.isoformat(),
        zonas_filtro,
        limite=5,
    )
    clientes_vendedor = adapt_actions_dataframe(clientes_vendedor)
    productos_vendedor = siscor_db.productos_a_impulsar(
        desde_sql,
        hasta_sql,
        accion_comparacion_desde.isoformat(),
        accion_comparacion_hasta.isoformat(),
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

    st.markdown(
        render_module_heading(
            "Mi avance del mes" if periodo == "Mes en curso" else "Mi avance del periodo",
            "Resumen del objetivo, ritmo y ticket de la zona",
            "sales",
            "$",
        ),
        unsafe_allow_html=True,
    )
    if vendedor_row is None:
        st.warning("Tu zona no tiene objetivo cargado para este mes.")
    else:
        if periodo == "Mes en curso":
            st.markdown(
                render_metric_grid(
                    [
                        ("Ventas mes", money(vendedor_row["ventas_mes"])),
                        ("Objetivo", money(vendedor_row["objetivo"])),
                        ("Cumplimiento", percent(vendedor_row["cumplimiento"])),
                        ("Diario necesario", money(vendedor_row["venta_diaria_necesaria"])),
                        ("Dias para vender", workdays(dias_restantes)),
                        ("Ritmo a la fecha", percent(vendedor_row["ritmo"])),
                        ("Proyeccion cierre", money(vendedor_row["proyeccion_cierre"])),
                        (
                            "Ticket promedio",
                            money(
                                numeric_value(vendedor_row["ventas_mes"])
                                / numeric_value(vendedor_row["comprobantes"])
                                if numeric_value(vendedor_row["comprobantes"])
                                else 0
                            ),
                        ),
                    ]
                ),
                unsafe_allow_html=True,
            )
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
            objetivo_mensual = numeric_value(vendedor_row["objetivo"])
            meta_periodo = (
                numeric_value(vendedor_row["objetivo"]) * dias_periodo_objetivo / dias_mes_objetivo
                if dias_mes_objetivo
                else 0
            )
            cumplimiento_objetivo = ventas_periodo_total / objetivo_mensual if objetivo_mensual else 0
            ritmo_periodo = ventas_periodo_total / meta_periodo if meta_periodo else 0
            comprobantes_periodo = (
                ventas_periodo_vendedor["comprobantes"].sum()
                if not ventas_periodo_vendedor.empty
                else 0
            )
            ticket_promedio_periodo = (
                ventas_periodo_total / comprobantes_periodo if comprobantes_periodo else 0
            )

            st.markdown(
                render_metric_grid(
                    [
                        ("Ventas periodo", money(ventas_periodo_total)),
                        ("Objetivo mensual", money(objetivo_mensual)),
                        ("Cumplimiento objetivo", percent(cumplimiento_objetivo)),
                        ("Meta a la fecha", money(meta_periodo)),
                        ("Ritmo periodo", percent(ritmo_periodo)),
                        ("Diario necesario mes", money(vendedor_row["venta_diaria_necesaria"])),
                        ("Ticket promedio", money(ticket_promedio_periodo)),
                    ]
                ),
                unsafe_allow_html=True,
            )
            st.caption(
                "La meta a la fecha es proporcional a los dias comerciales seleccionados; el objetivo mensual no cambia."
            )

    st.markdown(
        render_module_heading(
            "Recomendacion rapida",
            "Clientes y producto foco para revisar hoy",
            "action",
            "!",
        ),
        unsafe_allow_html=True,
    )
    st.info(
        seller_action_message(
            vendedor_row,
            clientes_vendedor,
            productos_vendedor,
            zonas_filtro,
            top_clientes_vendedor,
        )
    )

    st.markdown(
        render_module_heading(
            "Detalle vendedor",
            "Plan de accion, clientes y productos principales",
            "detail",
            "D",
        ),
        unsafe_allow_html=True,
    )

    seccion_vendedor = st.radio(
        "Detalle vendedor",
        ["Plan de accion", "Clientes", "Productos"],
        index=0,
        horizontal=True,
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

    st.markdown(
        render_module_heading(
            "Estrategia cliente",
            "Busca un cliente y revisa historial, credito y productos",
            "strategy",
            "E",
        ),
        unsafe_allow_html=True,
    )
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
        resumen_periodo_cliente, _, _ = siscor_db.estrategia_cliente(
            cliente_seleccionado,
            desde_sql,
            hasta_sql,
            cliente_comparacion_desde.isoformat(),
            cliente_comparacion_hasta.isoformat(),
            zonas_filtro,
        )
        resumen_historial_cliente, productos_cliente, caidos_cliente = siscor_db.estrategia_cliente(
            cliente_seleccionado,
            historial_cliente_desde.isoformat(),
            historial_cliente_hasta.isoformat(),
            historial_cliente_anterior_desde.isoformat(),
            historial_cliente_anterior_hasta.isoformat(),
            zonas_filtro,
        )
        resumen_row = resumen_periodo_cliente.iloc[0]
        resumen_historial_row = resumen_historial_cliente.iloc[0]
        venta_mes_cliente = numeric_value(resumen_row["venta_mes"])
        venta_anterior_cliente = numeric_value(resumen_row["venta_mes_anterior"])
        ultima_compra = resumen_historial_row["ultima_compra"]
        ultima_compra_texto = "Sin movimiento" if pd.isna(ultima_compra) else pd.to_datetime(ultima_compra).strftime("%d/%m/%Y")
        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Venta periodo", money(venta_mes_cliente))
        ec2.metric(cliente_comparacion_label, money(venta_anterior_cliente))
        ec3.metric("Variacion", money(venta_mes_cliente - venta_anterior_cliente))
        ec4.metric("Ultimo movimiento", ultima_compra_texto)

        credito_cliente = siscor_db.cliente_credito(cliente_seleccionado, zonas_filtro)
        if not credito_cliente.empty:
            credito_row = credito_cliente.iloc[0]
            st.markdown(
                render_module_heading(
                    "Perfil de credito sugerido",
                    "Deuda actual y condiciones recomendadas",
                    "credit",
                    "C",
                ),
                unsafe_allow_html=True,
            )
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
            st.markdown(
                render_module_heading(
                    "Productos habituales",
                    "Lo que el cliente suele comprar",
                    "detail",
                    "P",
                ),
                unsafe_allow_html=True,
            )
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
            st.markdown(
                render_module_heading(
                    "Productos caidos",
                    "Oportunidades para recuperar rotacion",
                    "products",
                    "R",
                ),
                unsafe_allow_html=True,
            )
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
    avance_objetivo = proporcion_objetivo
    dias_objetivo = max(dias_mes_referencia - dias_periodo_objetivo, 1.0)
    dias_display_objetivo = dias_periodo_objetivo
    objetivo_titulo = "Objetivos y ritmo del periodo"
    label_cumplimiento = "Cumplimiento objetivo"
    label_ritmo_esperado = "Peso del periodo"
    label_proyeccion = "Proyeccion de cierre"
    label_brecha = "Brecha proyectada"
    label_diario = "Venta diaria necesaria"
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
insights = {
    "leader": None,
    "risk": None,
    "recovery_daily": 0.0,
    "below_pace": 0,
    "message": "No hay objetivos cargados para el mes.",
}
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
    if periodo == "Mes en curso":
        c3.metric("Ritmo del equipo", percent(ritmo_total))
        c4.metric("Zonas en ritmo", f"{zonas_en_ritmo}/{len(desempeno_con_objetivo)}")
    else:
        c3.metric("Meta a la fecha", money(total_objetivo_esperado))
        c4.metric("Zonas en ritmo", f"{zonas_en_ritmo}/{len(desempeno_con_objetivo)}")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric(label_proyeccion, money(total_proyeccion))
    p2.metric(label_brecha, money(total_proyeccion - total_objetivo))
    p3.metric(label_diario, money(venta_diaria_necesaria))
    if periodo == "Mes en curso":
        p4.metric(label_dias, workdays(dias_display_objetivo))
    else:
        p4.metric("Objetivo mensual", money(total_objetivo))

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
plan_diario = build_daily_plan(radar_acciones)
st.subheader("Sala de decisiones")
st.markdown(
    render_decision_room(
        total_ventas_mes,
        total_objetivo,
        ritmo_total,
        total_proyeccion - total_objetivo,
        venta_diaria_necesaria,
        insights,
        plan_diario,
    ),
    unsafe_allow_html=True,
)

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
