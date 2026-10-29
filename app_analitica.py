from __future__ import annotations

from datetime import date, datetime
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import analytics_db
from src.analytics_print import PRINT_CSS, render_print_report


APP_NAME = "Bruncas Analitica"
SELLER_ZONE_ORDER = (
    "BRAVO",
    "CARINA",
    "DAVID",
    "JUAN C. MANZELLI",
    "LUCIA MORENO",
    "MACA PROTTO",
    "MICAELA GONZALEZ",
    "NOELIA",
    "ZONA 13 JAVIER MOLARO",
)
MONTH_NAMES = {
    1: "Ene",
    2: "Feb",
    3: "Mar",
    4: "Abr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dic",
}


st.set_page_config(page_title=APP_NAME, page_icon="assets/bruncas_analitica.ico", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --ba-bg: #f4f7f6;
        --ba-panel: #ffffff;
        --ba-line: #d9e3df;
        --ba-text: #18241f;
        --ba-muted: #66756f;
        --ba-green: #087f5b;
        --ba-gold: #d8af22;
        --ba-purple: #8e168f;
    }
    .stApp { background: var(--ba-bg); color: var(--ba-text); }
    [data-testid="stSidebar"] { background: #fbfcfc; border-right: 1px solid var(--ba-line); }
    [data-testid="stMetric"] {
        background: var(--ba-panel);
        border: 1px solid var(--ba-line);
        border-radius: 6px;
        padding: 8px 12px;
        min-height: 70px;
        box-shadow: inset 0 3px 0 #087f5b, 0 5px 16px rgba(24, 36, 31, .04);
    }
    [data-testid="stMetricLabel"] { color: var(--ba-muted); }
    [data-testid="stMetricValue"] { color: var(--ba-text); font-size: 1.25rem; }
    [data-testid="stMetricLabel"] p { font-size: .8rem; }
    .ba-brand { font-size: 1.15rem; font-weight: 750; color: var(--ba-text); margin-bottom: .15rem; }
    .ba-brand span { color: var(--ba-gold); }
    .ba-kicker { color: var(--ba-green); font-size: .78rem; font-weight: 700; text-transform: uppercase; }
    .ba-title { font-size: 1.8rem; font-weight: 760; margin: .2rem 0 0; }
    .ba-subtitle { color: var(--ba-muted); margin: .2rem 0 1.15rem; }
    .ba-freshness { color: var(--ba-muted); font-size: .82rem; text-align: right; padding-top: .45rem; }
    div[data-testid="stDataFrame"] { border: 1px solid var(--ba-line); border-radius: 6px; overflow: hidden; }
    div[data-testid="stPlotlyChart"] {
        background: var(--ba-panel);
        border: 1px solid var(--ba-line);
        border-radius: 6px;
        box-shadow: 0 8px 22px rgba(24, 36, 31, .05);
        overflow: hidden;
    }
    .ba-observation {
        margin-top: 1.35rem;
        background: #ffffff;
        border: 1px solid var(--ba-line);
        border-left: 5px solid var(--ba-green);
        border-radius: 6px;
        padding: 20px 22px;
        box-shadow: 0 8px 22px rgba(24, 36, 31, .05);
    }
    .ba-observation-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .ba-observation-title { font-size: 1.08rem; font-weight: 760; }
    .ba-badge { border-radius: 999px; padding: 5px 10px; font-size: .75rem; font-weight: 750; white-space: nowrap; }
    .ba-badge-positive { background: #e6f5ef; color: #087f5b; }
    .ba-badge-warning { background: #fff1e6; color: #ad4e00; }
    .ba-badge-neutral { background: #eef2f0; color: #53635d; }
    .ba-observation-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }
    .ba-observation-stat { border-top: 1px solid var(--ba-line); padding-top: 11px; }
    .ba-observation-label { color: var(--ba-muted); font-size: .78rem; }
    .ba-observation-value { color: var(--ba-text); font-size: 1.05rem; font-weight: 720; margin-top: 3px; }
    .ba-observation-copy { color: #43514c; line-height: 1.55; margin: 0; }
    @media (max-width: 760px) {
        .ba-observation-grid { grid-template-columns: 1fr; }
        .ba-observation-head { align-items: flex-start; flex-direction: column; }
    }
    @media print {
        [data-testid="stSidebar"], [data-testid="stHeader"] { display: none !important; }
        .main .block-container { max-width: 100% !important; padding: 12px !important; }
        [data-testid="stPlotlyChart"], [data-testid="stMetric"], .ba-observation { box-shadow: none !important; }
    }
    .stButton button { border-radius: 6px; font-weight: 650; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(f"<style>{PRINT_CSS}</style>", unsafe_allow_html=True)


def month_label(value: str) -> str:
    stamp = pd.Timestamp(f"{value}-01")
    return f"{MONTH_NAMES[stamp.month]} {stamp.year}"


def money(value: float) -> str:
    return f"$ {value:,.0f}".replace(",", ".")


def number(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", ".")
    return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def compact_money(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        formatted = f"$ {value / 1_000_000:.1f} M"
    elif absolute >= 1_000:
        formatted = f"$ {value / 1_000:.1f} mil"
    else:
        formatted = f"$ {value:.0f}"
    return formatted.replace(".", ",")


def month_start_months_ago(months: int) -> date:
    current = pd.Timestamp(date.today().replace(day=1))
    return (current - pd.DateOffset(months=months)).date()


def comparison_periods(end: date) -> tuple[tuple[str, date, date], ...]:
    end_stamp = pd.Timestamp(end)
    current_period = end_stamp.to_period("M")
    is_partial_month = end_stamp.date() < current_period.end_time.date()
    closed_period = current_period - 1 if is_partial_month else current_period
    previous_period = closed_period - 1
    year_ago_period = closed_period - 12

    periods = [
        ("closed", closed_period.start_time.date(), closed_period.end_time.date()),
        ("previous", previous_period.start_time.date(), previous_period.end_time.date()),
        ("year_ago", year_ago_period.start_time.date(), year_ago_period.end_time.date()),
    ]
    if is_partial_month:
        elapsed_day = end_stamp.day
        previous_cut_period = current_period - 1
        year_cut_period = current_period - 12
        previous_cut_end = min(elapsed_day, previous_cut_period.days_in_month)
        year_cut_end = min(elapsed_day, year_cut_period.days_in_month)
        periods.extend(
            [
                ("current_cut", current_period.start_time.date(), end_stamp.date()),
                (
                    "previous_cut",
                    previous_cut_period.start_time.date(),
                    previous_cut_period.start_time.replace(day=previous_cut_end).date(),
                ),
                (
                    "year_cut",
                    year_cut_period.start_time.date(),
                    year_cut_period.start_time.replace(day=year_cut_end).date(),
                ),
            ]
        )
    return tuple(periods)


def complete_months(data: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    months = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M").astype(str)
    if data.empty:
        grouped = pd.DataFrame(
            columns=["mes", "facturacion", "unidades", "comprobantes", "clientes", "pagos", "recibos"]
        )
    else:
        grouped = (
            data.groupby("mes", as_index=False)
            .agg(
                facturacion=("facturacion", "sum"),
                unidades=("unidades", "sum"),
                comprobantes=("comprobantes", "sum"),
                clientes=("id_cliente", lambda values: values[data.loc[values.index, "facturacion"].ne(0)].nunique()),
                pagos=("pagos", "sum"),
                recibos=("recibos", "sum"),
            )
        )
    frame = pd.DataFrame({"mes": months}).merge(grouped, on="mes", how="left").fillna(0)
    frame["periodo"] = frame["mes"].map(month_label)
    return frame


def behavior_observation(
    monthly: pd.DataFrame,
    comparisons: pd.DataFrame,
    value_column: str,
    metric: str,
    end: date,
) -> dict[str, str]:
    total_invoiced = float(monthly["facturacion"].sum())
    total_paid = float(monthly["pagos"].sum())
    payment_ratio = 100 * total_paid / total_invoiced if total_invoiced > 0 else None
    payment_text = money(total_paid)
    if payment_ratio is not None:
        payment_text += f" · {payment_ratio:.0f}% de lo facturado"

    values = comparisons.set_index("periodo") if not comparisons.empty else pd.DataFrame()
    required = {"closed", "previous", "year_ago"}
    if values.empty or not required.issubset(values.index):
        return {
            "status": "Sin comparacion suficiente",
            "badge": "neutral",
            "month_change": "No hay meses comparables disponibles",
            "year_change": "No hay comparacion interanual disponible",
            "current_cut": "El mes en curso no puede compararse todavia",
            "payments": payment_text,
            "copy": "Amplia el periodo o revisa la disponibilidad de datos para obtener comparaciones equivalentes.",
        }

    end_stamp = pd.Timestamp(end)
    current_period = end_stamp.to_period("M")
    is_partial_month = end_stamp.date() < current_period.end_time.date()
    closed_period = current_period - 1 if is_partial_month else current_period
    previous_period = closed_period - 1
    year_ago_period = closed_period - 12

    def display_value(value: float) -> str:
        return money(value) if metric == "Facturacion" else f"{number(value)} unidades"

    def variation_text(current: float, baseline: float) -> str:
        if baseline == 0:
            return "sin base comparable" if current != 0 else "sin variacion"
        return f"{((current / baseline) - 1) * 100:+.1f}%".replace(".", ",")

    closed_value = float(values.loc["closed", value_column])
    previous_value = float(values.loc["previous", value_column])
    year_value = float(values.loc["year_ago", value_column])
    month_variation = None if previous_value == 0 else (closed_value / previous_value - 1) * 100
    if month_variation is None:
        status = "Sin comparacion suficiente"
    elif abs(month_variation) < 3:
        status = "Se mantuvo frente al mes anterior"
    elif month_variation > 0:
        status = "Subio frente al mes anterior"
    else:
        status = "Bajo frente al mes anterior"

    month_change = (
        f"{month_label(str(closed_period))}: {display_value(closed_value)} · "
        f"{variation_text(closed_value, previous_value)} vs {month_label(str(previous_period))}"
    )
    year_change = (
        f"{month_label(str(closed_period))}: {display_value(closed_value)} · "
        f"{variation_text(closed_value, year_value)} vs {month_label(str(year_ago_period))}"
    )

    current_cut = "Mes cerrado; no requiere comparacion parcial"
    if is_partial_month and {"current_cut", "previous_cut", "year_cut"}.issubset(values.index):
        current_value = float(values.loc["current_cut", value_column])
        previous_cut_value = float(values.loc["previous_cut", value_column])
        year_cut_value = float(values.loc["year_cut", value_column])
        current_cut = (
            f"1 al {end_stamp.day} de {month_label(str(current_period))}: {display_value(current_value)} · "
            f"{variation_text(current_value, previous_cut_value)} vs mes anterior · "
            f"{variation_text(current_value, year_cut_value)} interanual"
        )

    return {
        "status": status,
        "badge": "neutral",
        "month_change": month_change,
        "year_change": year_change,
        "current_cut": current_cut,
        "payments": payment_text,
        "copy": (
            "La variacion mensual describe el cambio inmediato. La comparacion con el mismo mes del ano anterior "
            "ayuda a distinguir estacionalidad de una mejora o baja real. El mes en curso usa exactamente los mismos dias transcurridos."
        ),
    }


with st.sidebar:
    st.markdown('<div class="ba-brand"><span>+</span>Bruncas Analitica</div>', unsafe_allow_html=True)
    st.caption("Lectura comercial local")
    st.divider()
    metric = st.radio("Metrica", ("Facturacion", "Unidades"), horizontal=True)

    try:
        clients = analytics_db.clientes_actuales()
    except Exception as exc:
        st.error("No se pudo consultar SisCor. Verifica que la red y SisCor esten disponibles.")
        st.exception(exc)
        st.stop()

    available_zones = set(clients["zona_actual"].dropna().astype(str).unique())
    ordered_zones = [zone for zone in SELLER_ZONE_ORDER if zone in available_zones]
    selected_zone = st.selectbox("Vendedor actual", ["Todos los vendedores", *ordered_zones])

    client_options = clients[clients["zona_actual"].isin(ordered_zones)]
    if selected_zone != "Todos los vendedores":
        client_options = client_options[client_options["zona_actual"].eq(selected_zone)]
    client_options = client_options.sort_values("cliente")
    labels = {
        f"{row.cliente} | {row.id_cliente}": str(row.id_cliente)
        for row in client_options.itertuples(index=False)
    }
    selected_client_label = st.selectbox("Cliente", ["Todos los clientes", *labels.keys()])
    selected_client_id = labels.get(selected_client_label)

    start_date = st.date_input("Desde", value=month_start_months_ago(12), max_value=date.today())
    end_date = st.date_input("Hasta", value=date.today(), max_value=date.today())
    if start_date > end_date:
        st.error("La fecha Desde no puede ser posterior a Hasta.")
        st.stop()

    if st.button("Actualizar datos", width="stretch", type="primary"):
        analytics_db.clear_cache()
        st.rerun()

st.markdown('<div class="ba-kicker">Evolucion mensual</div>', unsafe_allow_html=True)
st.markdown('<div class="ba-title">Comportamiento comercial</div>', unsafe_allow_html=True)
context_parts = []
if selected_zone != "Todos los vendedores":
    context_parts.append(selected_zone)
if selected_client_label != "Todos los clientes":
    context_parts.append(selected_client_label.split(" | ")[0])
context_text = " · ".join(context_parts) if context_parts else "Todos los vendedores y clientes"
st.markdown(f'<div class="ba-subtitle">{context_text}</div>', unsafe_allow_html=True)

try:
    with st.spinner("Consultando SisCor en modo lectura..."):
        period_sales = analytics_db.ventas_mensuales(
            start_date,
            end_date,
            None,
            None,
            tuple(ordered_zones),
        )
except Exception as exc:
    st.error("No se pudo obtener el historial comercial desde SisCor.")
    st.exception(exc)
    st.stop()

sales = period_sales
if selected_zone != "Todos los vendedores":
    sales = sales[sales["zona_actual"].eq(selected_zone)]
if selected_client_id:
    sales = sales[sales["id_cliente"].eq(selected_client_id)]

try:
    current_debt = analytics_db.deuda_actual(
        selected_zone if selected_zone != "Todos los vendedores" else None,
        selected_client_id,
        tuple(ordered_zones),
    )
    comparisons = analytics_db.resumen_periodos(
        comparison_periods(end_date),
        selected_zone if selected_zone != "Todos los vendedores" else None,
        selected_client_id,
        tuple(ordered_zones),
    )
except Exception as exc:
    st.error("No se pudo obtener el resumen actual desde SisCor.")
    st.exception(exc)
    st.stop()

monthly = complete_months(sales, start_date, end_date)
value_column = "facturacion" if metric == "Facturacion" else "unidades"
total_value = float(monthly[value_column].sum())
average_value = float(monthly[value_column].mean()) if not monthly.empty else 0
total_payments = float(monthly["pagos"].sum())

summary_cols = st.columns(4)
summary_cols[0].metric(f"{metric} del periodo", money(total_value) if metric == "Facturacion" else number(total_value))
summary_cols[1].metric("Promedio mensual", money(average_value) if metric == "Facturacion" else number(average_value))
summary_cols[2].metric("Pagos registrados", money(total_payments))
summary_cols[3].metric("Deuda actual", money(current_debt))

fig = go.Figure()
primary_labels = [
    (compact_money(float(value)) if metric == "Facturacion" else number(float(value))) if float(value) != 0 else ""
    for value in monthly[value_column]
]
payment_labels = [compact_money(float(value)) if float(value) != 0 else "" for value in monthly["pagos"]]
primary_positions = [
    "top center" if primary >= payment else "bottom center"
    for primary, payment in zip(monthly[value_column], monthly["pagos"])
]
payment_positions = ["bottom center" if position == "top center" else "top center" for position in primary_positions]
fig.add_trace(
    go.Scatter(
        x=monthly["periodo"],
        y=monthly[value_column],
        name=metric,
        mode="lines+markers+text",
        text=primary_labels,
        textposition=primary_positions if metric == "Facturacion" else "top center",
        textfont={"size": 10, "color": "#315148"},
        line={"color": "#087f5b", "width": 3},
        marker={"color": "#d8af22", "size": 8, "line": {"color": "#ffffff", "width": 2}},
        fill="tozeroy",
        fillcolor="rgba(8, 127, 91, 0.08)",
        hovertemplate=("%{x}<br>$ %{y:,.0f}<extra></extra>" if metric == "Facturacion" else "%{x}<br>%{y:,.0f} unidades<extra></extra>"),
    )
)
if metric == "Facturacion":
    fig.add_trace(
        go.Scatter(
            x=monthly["periodo"],
            y=monthly["pagos"],
            name="Pagos por recibos",
            mode="lines+markers+text",
            text=payment_labels,
            textposition=payment_positions,
            textfont={"size": 10, "color": "#7a237b"},
            line={"color": "#8e168f", "width": 2.5, "dash": "dash"},
            marker={"color": "#8e168f", "size": 7, "symbol": "square-open"},
            hovertemplate="%{x}<br>$ %{y:,.0f} pagados<extra></extra>",
        )
    )
else:
    fig.add_trace(
        go.Bar(
            x=monthly["periodo"],
            y=monthly["pagos"],
            name="Pagos por recibos",
            yaxis="y2",
            text=payment_labels,
            textposition="inside",
            insidetextanchor="end",
            textfont={"size": 9, "color": "#7a237b"},
            cliponaxis=False,
            marker={"color": "rgba(142, 22, 143, 0.24)"},
            hovertemplate="%{x}<br>$ %{y:,.0f} pagados<extra></extra>",
        )
    )
fig.update_layout(
    height=460,
    margin={"l": 16, "r": 18, "t": 68, "b": 18},
    title={"text": f"{metric} por mes", "font": {"size": 17}},
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    showlegend=True,
    legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    hovermode="x unified",
    font={"family": "Arial", "color": "#18241f"},
    xaxis={"showgrid": False, "tickangle": 0},
    yaxis={
        "gridcolor": "#e6ece9",
        "zerolinecolor": "#cbd7d2",
        "tickprefix": "$ " if metric == "Facturacion" else "",
        "rangemode": "tozero",
    },
)
if metric == "Unidades":
    fig.update_layout(
        yaxis2={
            "title": "Pagos ($)",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "rangemode": "tozero",
            "tickprefix": "$ ",
        }
    )
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

st.subheader("Detalle mensual")
detail = monthly.loc[
    :, ["periodo", "facturacion", "pagos", "unidades", "clientes", "comprobantes", "recibos"]
].rename(
    columns={
        "periodo": "Mes",
        "facturacion": "Facturacion",
        "pagos": "Pagos",
        "unidades": "Unidades",
        "clientes": "Clientes con compras",
        "comprobantes": "Comprobantes",
        "recibos": "Recibos",
    }
)
st.dataframe(
    detail,
    width="stretch",
    hide_index=True,
    column_config={
        "Facturacion": st.column_config.NumberColumn(format="$ %.0f"),
        "Pagos": st.column_config.NumberColumn(format="$ %.0f"),
        "Unidades": st.column_config.NumberColumn(format="%.1f"),
        "Clientes con compras": st.column_config.NumberColumn(format="%d"),
        "Comprobantes": st.column_config.NumberColumn(format="%d"),
        "Recibos": st.column_config.NumberColumn(format="%d"),
    },
)

observation = behavior_observation(monthly, comparisons, value_column, metric, end_date)
subject = selected_client_label.split(" | ")[0] if selected_client_label != "Todos los clientes" else context_text
st.markdown(
    f"""
    <div class="ba-observation">
        <div class="ba-observation-head">
            <div>
                <div class="ba-kicker">Resumen del comportamiento</div>
                <div class="ba-observation-title">{html.escape(subject)}</div>
            </div>
            <div class="ba-badge ba-badge-{observation['badge']}">{observation['status']}</div>
        </div>
        <div class="ba-observation-grid">
            <div class="ba-observation-stat">
                <div class="ba-observation-label">Mes cerrado vs mes anterior</div>
                <div class="ba-observation-value">{observation['month_change']}</div>
            </div>
            <div class="ba-observation-stat">
                <div class="ba-observation-label">Mismo mes del ano anterior</div>
                <div class="ba-observation-value">{observation['year_change']}</div>
            </div>
            <div class="ba-observation-stat">
                <div class="ba-observation-label">Mes en curso a igual cantidad de dias</div>
                <div class="ba-observation-value">{observation['current_cut']}</div>
            </div>
            <div class="ba-observation-stat">
                <div class="ba-observation-label">Pagos mediante recibos</div>
                <div class="ba-observation-value">{observation['payments']}</div>
            </div>
        </div>
        <p class="ba-observation-copy">{observation['copy']}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="ba-freshness">Consulta actualizada: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")} · SisCor solo lectura</div>',
    unsafe_allow_html=True,
)
st.markdown(
    render_print_report(monthly, detail, context_text, start_date, end_date, metric, current_debt, observation),
    unsafe_allow_html=True,
)
