from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import re
import unicodedata

import pandas as pd

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    Workbook = None
    Alignment = Border = Font = PatternFill = Side = None
    get_column_letter = None

from src import anura_api, clientify_api, objectives, persat_api, siscor_db
from src.simple_xlsx import build_workbook as build_simple_workbook


REPORTS_DIR = Path("data/informes_semanales")
REPORT_NAME_PATTERN = re.compile(r"Informe_Semanal_(\d{4}-\d{2}-\d{2})\.xlsx$")

DISPLAY_NAMES = {
    "ZONA 13 JAVIER MOLARO": "JAVIER",
    "JONATAN MERCAO": "JONATAN",
    "JUAN C. MANZELLI": "JUAN CRUZ",
    "MACA PROTTO": "MACARENA",
    "MICAELA GONZALEZ": "MICAELA",
    "LUCIA MORENO": "LUCIA",
}

COLORS = {
    "navy": "16324F",
    "teal": "0F766E",
    "green": "16804A",
    "blue": "2563A6",
    "amber": "D97706",
    "ink": "172033",
    "muted": "5B677A",
    "line": "D7DEE8",
    "panel": "F4F7FA",
    "note": "FFF4D6",
    "white": "FFFFFF",
    "red": "B42318",
}


@dataclass(frozen=True)
class WeeklyReportResult:
    enabled: bool
    message: str
    path: Path | None = None


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.upper() if char.isalnum())


def _display_name(zone: object) -> str:
    clean = str(zone or "").strip().upper()
    return DISPLAY_NAMES.get(clean, clean)


def _is_telemarketing(zone: object) -> bool:
    return anura_api.is_telemarketing_zone(zone)


def _anura_aliases(zone: str) -> set[str]:
    selected: set[str] = {_normalize(zone)}
    normalized_zone = _normalize(zone)
    for key, aliases in anura_api.TELEMARKETING_ACCOUNTS.items():
        candidates = (key, *aliases)
        normalized_candidates = {_normalize(value) for value in candidates}
        if any(
            normalized_zone == candidate
            or normalized_zone in candidate
            or candidate in normalized_zone
            for candidate in normalized_candidates
            if candidate
        ):
            selected.update(normalized_candidates)
    return selected


def _calls_for_zone(calls: pd.DataFrame, zone: str) -> int:
    if calls.empty:
        return 0
    aliases = _anura_aliases(zone)
    matches = pd.Series(False, index=calls.index)
    for column in ("interno", "telemarketer"):
        if column in calls.columns:
            matches |= calls[column].map(_normalize).isin(aliases)
    return int(matches.sum())


def _clientify_aliases(zone: str) -> tuple[str, ...]:
    normalized = _normalize(zone)
    if "DAVID" in normalized:
        return ("DAVID",)
    if "NOELIA" in normalized:
        return ("NOELIA",)
    if "MICAELA" in normalized:
        return ("MICAELA",)
    if any(token in normalized for token in ("MACA", "MACARENA", "PROTTO")):
        return ("MACA", "MACARENA", "PROTTO")
    if "LUCIA" in normalized:
        return ("LUCIA",)
    return (normalized,)


def _contacts_for_zone(by_owner: list[dict[str, object]], zone: str) -> int:
    aliases = _clientify_aliases(zone)
    total = 0
    for row in by_owner:
        owner = _normalize(row.get("telemarketer"))
        if any(_normalize(alias) in owner for alias in aliases if alias):
            contacts = pd.to_numeric(row.get("clientes"), errors="coerce")
            if pd.notna(contacts):
                total += int(contacts)
    return total


def _source_status(name: str, enabled: bool, message: str) -> str:
    if enabled:
        return f"{name}: OK"
    return f"{name}: no disponible ({message})"


def _activity_data(week_start: date, cutoff: date, zones: tuple[str, ...]) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    telemarketing_zones = tuple(zone for zone in zones if _is_telemarketing(zone))
    street_zones = tuple(zone for zone in zones if not _is_telemarketing(zone))

    anura_result = anura_api.calls(week_start.isoformat(), cutoff.isoformat(), telemarketing_zones)
    clientify_result = clientify_api.inbox_activity(
        week_start.isoformat(),
        cutoff.isoformat(),
        telemarketing_zones,
    )
    persat_zones = tuple(zone for zone in street_zones if str(zone).strip().upper() in persat_api.ZONE_DEVICE_MAP)
    persat_result = persat_api.activity(week_start.isoformat(), cutoff.isoformat(), persat_zones)

    for zone in telemarketing_zones:
        output[zone] = {
            "modalidad": "Telemarketing",
            "llamadas": _calls_for_zone(anura_result.calls, zone) if anura_result.enabled else None,
            "contactos": _contacts_for_zone(clientify_result.by_owner, zone) if clientify_result.enabled else None,
            "visitas": None,
            "fuentes_actividad": " | ".join(
                [
                    _source_status("Anura", anura_result.enabled, anura_result.message),
                    _source_status("Clientify", clientify_result.enabled, clientify_result.message),
                ]
            ),
        }

    for zone in street_zones:
        device_ids = persat_api.ZONE_DEVICE_MAP.get(str(zone).strip().upper(), ())
        if not device_ids:
            output[zone] = {
                "modalidad": "Vendedor de calle",
                "llamadas": None,
                "contactos": None,
                "visitas": None,
                "fuentes_actividad": "Persat: sin dispositivo asociado a esta zona",
            }
            continue
        visits = persat_result.visits
        visit_count = None
        if persat_result.enabled:
            visit_count = int(visits["device_id"].isin(device_ids).sum()) if not visits.empty else 0
        output[zone] = {
            "modalidad": "Vendedor de calle",
            "llamadas": None,
            "contactos": None,
            "visitas": visit_count,
            "fuentes_actividad": _source_status("Persat", persat_result.enabled, persat_result.message),
        }

    return output


def collect_report_data(cutoff: date) -> tuple[pd.DataFrame, date, date]:
    month_start = cutoff.replace(day=1)
    week_start = cutoff - timedelta(days=cutoff.weekday())
    month = objectives.month_key(cutoff)
    objective_rows = objectives.load_objectives()
    objective_rows = objective_rows[objective_rows["mes"].eq(month)].copy()
    if objective_rows.empty:
        raise RuntimeError(f"No hay objetivos cargados para {month}.")

    zones = tuple(objective_rows["zona"].dropna().astype(str))
    sales = siscor_db.ventas_por_zona(month_start.isoformat(), cutoff.isoformat(), zones)
    units = siscor_db.unidades_por_zona(month_start.isoformat(), cutoff.isoformat(), zones)
    activity = _activity_data(week_start, cutoff, zones)

    base = objective_rows.loc[:, ["zona", "objetivo"]].copy()
    sales_columns = ["zona", "total", "comprobantes", "clientes"]
    sales = sales.reindex(columns=sales_columns)
    base = base.merge(sales, on="zona", how="left")
    base = base.merge(units.reindex(columns=["zona", "unidades"]), on="zona", how="left")
    for column in ("objetivo", "total", "comprobantes", "clientes", "unidades"):
        base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0)
    base["cumplimiento"] = base.apply(
        lambda row: float(row["total"] / row["objetivo"]) if row["objetivo"] else 0.0,
        axis=1,
    )
    base["ticket_promedio"] = base.apply(
        lambda row: float(row["total"] / row["comprobantes"]) if row["comprobantes"] else 0.0,
        axis=1,
    )
    base["nombre"] = base["zona"].map(_display_name)
    base["modalidad"] = base["zona"].map(lambda zone: activity[str(zone)]["modalidad"])
    for column in ("llamadas", "contactos", "visitas", "fuentes_actividad"):
        base[column] = base["zona"].map(lambda zone, key=column: activity[str(zone)][key])
    return base.sort_values("nombre").reset_index(drop=True), month_start, week_start


def _merge_value(sheet, address: str, value: object) -> None:
    sheet.merge_cells(address)
    sheet[address.split(":", 1)[0]] = value


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _style_merged(
    sheet,
    address: str,
    *,
    fill: str,
    color: str,
    size: int,
    bold: bool = False,
    horizontal: str = "center",
) -> None:
    thin = Side(style="thin", color=COLORS["line"])
    for row in sheet[address]:
        for cell in row:
            cell.fill = _fill(fill)
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    cell = sheet[address.split(":", 1)[0]]
    cell.font = Font(name="Aptos", size=size, bold=bold, color=color)
    cell.alignment = Alignment(horizontal=horizontal, vertical="center", wrap_text=True)


def _write_seller_sheet(sheet, row: pd.Series, cutoff: date, month_start: date, week_start: date) -> None:
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A5"
    sheet.print_area = "A1:J19"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.sheet_properties.outlinePr.summaryBelow = True
    for column in range(1, 11):
        sheet.column_dimensions[get_column_letter(column)].width = 14

    _merge_value(sheet, "A1:J1", "INFORME SEMANAL DE DESEMPEÑO")
    _style_merged(sheet, "A1:J1", fill=COLORS["navy"], color=COLORS["white"], size=18, bold=True)
    _merge_value(sheet, "A2:J2", f"{row['nombre']}  |  {row['modalidad']}")
    _style_merged(sheet, "A2:J2", fill=COLORS["navy"], color=COLORS["white"], size=12, bold=True)
    period = (
        f"Corte: {cutoff:%d/%m/%Y}  |  Ventas: {month_start:%d/%m/%Y} al {cutoff:%d/%m/%Y}"
        f"  |  Actividad: {week_start:%d/%m/%Y} al {cutoff:%d/%m/%Y}"
    )
    _merge_value(sheet, "A3:J3", period)
    _style_merged(sheet, "A3:J3", fill="E8EEF5", color=COLORS["ink"], size=10)
    _merge_value(sheet, "A4:J4", f"Zona SisCor: {row['zona']}")
    _style_merged(sheet, "A4:J4", fill=COLORS["note"], color="8A4B08", size=9, bold=True)

    _merge_value(sheet, "A6:J6", "RESULTADO COMERCIAL ACUMULADO DEL MES")
    _style_merged(sheet, "A6:J6", fill=COLORS["teal"], color=COLORS["white"], size=11, bold=True, horizontal="left")

    cards = [
        ("A7:B7", "A8:B9", "Objetivo mensual", float(row["objetivo"]), COLORS["navy"], '"$"#,##0'),
        ("C7:D7", "C8:D9", "Facturación acumulada", float(row["total"]), COLORS["blue"], '"$"#,##0'),
        ("E7:F7", "E8:F9", "% de cumplimiento", float(row["cumplimiento"]), COLORS["green"], "0.0%"),
        ("G7:H7", "G8:H9", "Unidades vendidas", float(row["unidades"]), COLORS["amber"], "#,##0"),
        ("I7:J7", "I8:J9", "Ticket promedio", float(row["ticket_promedio"]), "6B5B95", '"$"#,##0'),
    ]
    for label_address, value_address, label, value, color, number_format in cards:
        _merge_value(sheet, label_address, label)
        _style_merged(sheet, label_address, fill=color, color=COLORS["white"], size=9, bold=True)
        _merge_value(sheet, value_address, value)
        _style_merged(sheet, value_address, fill=COLORS["panel"], color=COLORS["ink"], size=15, bold=True)
        sheet[value_address.split(":", 1)[0]].number_format = number_format

    _merge_value(sheet, "A11:J11", "ACTIVIDAD DE LA SEMANA")
    _style_merged(sheet, "A11:J11", fill=COLORS["teal"], color=COLORS["white"], size=11, bold=True, horizontal="left")
    if row["modalidad"] == "Telemarketing":
        activity_cards = [
            ("A13:E13", "A14:E15", "Llamadas realizadas (Anura)", row["llamadas"], COLORS["blue"]),
            ("F13:J13", "F14:J15", "Contactos únicos (Clientify)", row["contactos"], COLORS["green"]),
        ]
    else:
        activity_cards = [
            ("A13:J13", "A14:J15", "Visitas registradas (Persat)", row["visitas"], COLORS["amber"]),
        ]
    for label_address, value_address, label, value, color in activity_cards:
        _merge_value(sheet, label_address, label)
        _style_merged(sheet, label_address, fill=color, color=COLORS["white"], size=10, bold=True)
        _merge_value(sheet, value_address, "N/D" if pd.isna(value) else int(value))
        _style_merged(sheet, value_address, fill=COLORS["panel"], color=COLORS["ink"], size=18, bold=True)
        if not pd.isna(value):
            sheet[value_address.split(":", 1)[0]].number_format = "#,##0"

    _merge_value(sheet, "A17:J17", "FUENTES DEL INFORME")
    _style_merged(sheet, "A17:J17", fill="E8EEF5", color=COLORS["navy"], size=9, bold=True, horizontal="left")
    sources = f"SisCor (solo lectura): facturación, comprobantes y unidades | {row['fuentes_actividad']}"
    _merge_value(sheet, "A18:J18", sources)
    _style_merged(sheet, "A18:J18", fill=COLORS["white"], color=COLORS["muted"], size=9, horizontal="left")
    _merge_value(sheet, "A19:J19", f"Generado por Bruncas Comercial el {datetime.now():%d/%m/%Y %H:%M}")
    _style_merged(sheet, "A19:J19", fill=COLORS["white"], color=COLORS["muted"], size=8, horizontal="left")

    for row_number, height in {1: 32, 2: 24, 3: 22, 4: 21, 6: 23, 7: 23, 8: 28, 9: 28, 11: 23, 13: 23, 14: 29, 15: 29, 17: 22, 18: 27, 19: 20}.items():
        sheet.row_dimensions[row_number].height = height


def build_workbook(data: pd.DataFrame, cutoff: date, month_start: date, week_start: date) -> bytes:
    if Workbook is None:
        return build_simple_workbook(data, cutoff, month_start, week_start)
    workbook = Workbook()
    workbook.remove(workbook.active)
    used_titles: set[str] = set()
    for _, row in data.iterrows():
        base_title = re.sub(r"[\\/*?:\[\]]", " ", str(row["nombre"])).strip()[:31] or "Vendedor"
        title = base_title
        suffix = 2
        while title in used_titles:
            title = f"{base_title[:27]} {suffix}"
            suffix += 1
        used_titles.add(title)
        sheet = workbook.create_sheet(title)
        _write_seller_sheet(sheet, row, cutoff, month_start, week_start)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def report_filename(cutoff: date) -> str:
    return f"Informe_Semanal_{cutoff:%Y-%m-%d}.xlsx"


def generate_report(cutoff: date | None = None, output_dir: Path = REPORTS_DIR) -> WeeklyReportResult:
    cutoff = cutoff or date.today()
    try:
        data, month_start, week_start = collect_report_data(cutoff)
        content = build_workbook(data, cutoff, month_start, week_start)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / report_filename(cutoff)
        temporary = path.with_suffix(".xlsx.tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        return WeeklyReportResult(True, "OK", path)
    except Exception as exc:
        return WeeklyReportResult(False, str(exc), None)


def list_reports(output_dir: Path = REPORTS_DIR) -> list[Path]:
    if not output_dir.exists():
        return []
    return sorted(
        (path for path in output_dir.glob("Informe_Semanal_*.xlsx") if REPORT_NAME_PATTERN.match(path.name)),
        key=lambda path: path.name,
        reverse=True,
    )


def latest_report(output_dir: Path = REPORTS_DIR) -> Path | None:
    reports = list_reports(output_dir)
    return reports[0] if reports else None
