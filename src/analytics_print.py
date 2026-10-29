from __future__ import annotations

from datetime import date
import html

import pandas as pd


PRINT_CSS = """
.ba-print-report { display: none; }
@media print {
    @page { size: A4 portrait; margin: 8mm; }
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background: white !important; height: auto !important; overflow: visible !important;
    }
    [data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="stHorizontalBlock"], [data-baseweb="popover"], [role="dialog"],
    [data-testid="stDateInput"] + div, footer { display: none !important; }
    [data-testid="stElementContainer"]:not(:has(.ba-print-report)) { display: none !important; }
    [data-testid="stMainBlockContainer"], .block-container {
        width: 100% !important; max-width: none !important; padding: 0 !important;
    }
    [data-testid="stVerticalBlock"] { gap: 0 !important; }
    .ba-print-report { display: block !important; color: #18241f; font: 8pt Arial, sans-serif; }
    .ba-print-report h1 { font-size: 14pt; margin: 0 0 2mm; }
    .ba-print-report h2 { font-size: 10pt; margin: 3mm 0 2mm; }
    .ba-print-report p { margin: 1mm 0; line-height: 1.3; }
    .ba-print-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2mm; margin: 3mm 0; }
    .ba-print-metric { padding: 2mm; border: 1px solid #cbd7d2; }
    .ba-print-metric span { display: block; font-size: 7pt; }
    .ba-print-metric strong { display: block; font-size: 11pt; margin-top: 1mm; }
    .ba-print-chart { width: 100%; height: auto; display: block; }
    .ba-print-report table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 8pt; }
    .ba-print-report th, .ba-print-report td { border: 1px solid #cbd7d2; padding: 1.1mm 1mm; text-align: right; overflow-wrap: anywhere; }
    .ba-print-report th { background: #e4f1ed; font-size: 7.5pt; }
    .ba-print-report th:first-child, .ba-print-report td:first-child { text-align: left; }
    .ba-print-report tr, .ba-print-report table, .ba-print-summary { break-inside: avoid; }
    .ba-print-summary { margin-top: 3mm; padding-top: 2mm; border-top: 1px solid #087f5b; }
    .ba-print-comparisons { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1mm 3mm; margin: 2mm 0; }
    .ba-print-source { color: #53635d; font-size: 7pt; margin-top: 3mm !important; }
}
"""


def _number(value: float, currency: bool = False) -> str:
    if not currency and not float(value).is_integer():
        return f"{float(value):,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    amount = f"{float(value):,.0f}".replace(",", ".")
    return f"$ {amount}" if currency else amount


def _label(value: float, currency: bool) -> str:
    if not currency:
        return _number(value)
    if abs(value) >= 1_000_000:
        return f"$ {value / 1_000_000:.1f}M".replace(".", ",")
    if abs(value) >= 1_000:
        return f"$ {value / 1_000:.0f}k"
    return _number(value, True)


def _chart(monthly: pd.DataFrame, metric: str) -> str:
    column = "facturacion" if metric == "Facturacion" else "unidades"
    series = [(metric, monthly[column].astype(float).tolist(), "#111111", metric == "Facturacion"),
              ("Cobranza por recibos ($)", monthly["pagos"].astype(float).tolist(), "#555555", True)]
    months = monthly["periodo"].astype(str).tolist()
    parts = ['<svg class="ba-print-chart" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 260" role="img" aria-label="Evolucion mensual">']
    for y in (55, 95, 135, 175, 215):
        parts.append(f'<line x1="30" y1="{y}" x2="970" y2="{y}" stroke="#e1e8e4"/>')
    shared = [value for _, values, _, _ in series for value in values]
    for index, (name, values, color, currency) in enumerate(series):
        scale = shared if metric == "Facturacion" else values
        low, high = min([0.0, *scale]), max([0.0, *scale])
        spread = high - low or 1.0
        points = [(30 + i * 940 / max(1, len(values) - 1), 215 - (value - low) * 160 / spread) for i, value in enumerate(values)]
        legend_x = 30 + index * 450
        dash = ' stroke-dasharray="9 5"' if index else ''
        parts.append(f'<line x1="{legend_x}" y1="15" x2="{legend_x + 45}" y2="15" stroke="{color}" stroke-width="2.5"{dash}/>')
        if index:
            parts.append(f'<rect x="{legend_x + 19}" y="11" width="8" height="8" fill="white" stroke="{color}" stroke-width="2"/>')
        else:
            parts.append(f'<circle cx="{legend_x + 23}" cy="15" r="4" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 55}" y="20" fill="{color}" font-family="Arial" font-size="15">{html.escape(name)}' + (' (escala propia)' if metric == "Unidades" else '') + '</text>')
        coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.5"{dash}/>')
        for i, ((x, y), value) in enumerate(zip(points, values)):
            if index:
                parts.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" fill="white" stroke="{color}" stroke-width="1.5"/>')
            else:
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
            if value:
                above = index == 0
                if metric == "Facturacion":
                    above = (series[0][1][i] >= series[1][1][i]) == (index == 0)
                label_y = max(38, min(233, y + (-10 if above else 16)))
                anchor = "start" if i == 0 else "end" if i == len(values) - 1 else "middle"
                parts.append(f'<text x="{x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" fill="{color}" font-family="Arial" font-size="10">{html.escape(_label(value, currency))}</text>')
    for i, month in enumerate(months):
        x = 30 + i * 940 / max(1, len(months) - 1)
        anchor = "start" if i == 0 else "end" if i == len(months) - 1 else "middle"
        chunks = month.rsplit(" ", 1)
        label = html.escape(chunks[0])
        if len(chunks) == 2:
            label += f'<tspan x="{x:.1f}" dy="11">{html.escape(chunks[1])}</tspan>'
        parts.append(f'<text x="{x:.1f}" y="242" text-anchor="{anchor}" font-family="Arial" font-size="10">{label}</text>')
    return "".join(parts) + "</svg>"


def render_print_report(monthly: pd.DataFrame, detail: pd.DataFrame, subject: str,
                        start: date, end: date, metric: str, debt: float,
                        observation: dict[str, str]) -> str:
    column = "facturacion" if metric == "Facturacion" else "unidades"
    values = monthly[column].astype(float)
    metrics = [(f"{metric} del periodo", _number(values.sum(), metric == "Facturacion")),
               ("Promedio mensual", _number(values.mean() if len(values) else 0, metric == "Facturacion")),
               ("Pagos registrados", _number(monthly["pagos"].sum(), True)),
               ("Deuda actual", _number(debt, True))]
    cards = "".join(f'<div class="ba-print-metric"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>' for label, value in metrics)
    formatted = detail.copy()
    for name in formatted.columns:
        if name != "Mes":
            formatted[name] = formatted[name].map(lambda value: _number(value, name in {"Facturacion", "Pagos"}))
    table = formatted.to_html(index=False, escape=True, border=0)
    comparisons = [("Mes cerrado vs anterior", "month_change"), ("Mismo mes del ano anterior", "year_change"),
                   ("Mes en curso a igual corte", "current_cut"), ("Pagos mediante recibos", "payments")]
    stats = "".join(f'<div>{html.escape(label)}: <strong>{html.escape(str(observation[key]))}</strong></div>' for label, key in comparisons)
    return (
        '<div class="ba-print-report"><h1>Bruncas Analitica</h1>'
        f'<p><strong>{html.escape(subject)}</strong> | {start:%d/%m/%Y} al {end:%d/%m/%Y}</p>'
        f'<div class="ba-print-metrics">{cards}</div>{_chart(monthly, metric)}'
        f'<h2>Detalle mensual</h2>{table}'
        f'<div class="ba-print-summary"><h2>Resumen del comportamiento: {html.escape(str(observation["status"]))}</h2>'
        f'<div class="ba-print-comparisons">{stats}</div><p>{html.escape(str(observation["copy"]))}</p></div>'
        '<p class="ba-print-source">SisCor solo lectura. Facturacion y unidades netas; pagos registrados por recibos.</p></div>'
    )
