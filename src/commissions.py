from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd

from src import siscor_db

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = ValueError


COMMISSIONS_DIR = Path("data/comisiones")
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

USER_VENDOR_MAP = {
    "bravo": "Bravo",
    "carina": "Carina",
    "david": "David",
    "francisco": "Francisco",
    "javier": "Javier",
    "jonatan": "Jonatan",
    "juan": "Juan Cruz M.",
    "juancruz": "Juan Cruz M.",
    "julio": "Julio M.",
    "lucia": "Lucia",
    "maca": "Macarena",
    "micaela": "Micaela",
    "noelia": "Noelia",
}

AUTHORIZED_USERS = set(USER_VENDOR_MAP)
COMMISSIONED_USERS = {"carina", "francisco", "jonatan", "juan", "juancruz", "micaela"}
COMMISSIONED_VENDORS = {"Carina", "Francisco", "Jonatan", "Juan Cruz M.", "Micaela"}


@dataclass(frozen=True)
class CommissionResult:
    enabled: bool
    message: str
    source_name: str
    data: pd.DataFrame


def user_can_view(username: str, is_admin: bool = False) -> bool:
    return is_admin or str(username).strip().lower() in AUTHORIZED_USERS


def user_earns_commission(username: str) -> bool:
    return str(username).strip().lower() in COMMISSIONED_USERS


def vendor_earns_commission(vendor: object) -> bool:
    normalized = str(vendor or "").strip().upper().replace(".", "")
    commissioned = {value.upper().replace(".", "") for value in COMMISSIONED_VENDORS}
    return normalized in commissioned or normalized == "JUAN CRUZ"


def vendor_for_user(username: str) -> str | None:
    return USER_VENDOR_MAP.get(str(username).strip().lower())


def _col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for char in letters:
        value = value * 26 + ord(char.upper()) - 64
    return max(value - 1, 0)


def _shared_strings(zip_file: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for item in root.findall("x:si", NS):
        values.append("".join(node.text or "" for node in item.findall(".//x:t", NS)))
    return values


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    inline = cell.find("x:is/x:t", NS)
    if inline is not None:
        return inline.text or ""

    value = cell.find("x:v", NS)
    if value is None:
        return ""
    raw = value.text or ""
    if cell.attrib.get("t") == "s":
        return shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else raw
    return raw


def _workbook_sheets(zip_file: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(zip_file.read("xl/workbook.xml"))
    rels = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels
        if rel.tag.endswith("Relationship")
    }
    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall(".//x:sheet", NS):
        name = sheet.attrib.get("name", "Hoja")
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = rel_map.get(rel_id, "")
        if not target:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        elif target.startswith("xl/"):
            path = target
        else:
            path = "xl/" + target
        sheets.append((name, path))
    return sheets


def _sheet_rows(zip_file: zipfile.ZipFile, sheet_path: str, shared: list[str]) -> list[list[str]]:
    root = ET.fromstring(zip_file.read(sheet_path))
    rows: list[list[str]] = []
    for row_node in root.findall(".//x:sheetData/x:row", NS):
        row: list[str] = []
        for cell in row_node.findall("x:c", NS):
            index = _col_index(cell.attrib.get("r", "A1"))
            while len(row) <= index:
                row.append("")
            row[index] = _cell_value(cell, shared)
        rows.append(row)
    return rows


def _read_xlsx_bytes(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
        shared = _shared_strings(zip_file)
        sheets = _workbook_sheets(zip_file)
        resumen_path = next((path for name, path in sheets if name.strip().lower() == "resumen"), sheets[0][1])
        rows = _sheet_rows(zip_file, resumen_path, shared)

    header_index = next(
        (index for index, row in enumerate(rows) if row and row[0].strip().lower() == "vendedor"),
        None,
    )
    if header_index is None:
        return pd.DataFrame(columns=["vendedor", "comision_cobranza", "comision_ventas", "ventas_acumuladas"])

    headers = [value.strip().lower() for value in rows[header_index]]
    parsed_rows: list[dict[str, object]] = []
    for row in rows[header_index + 1 :]:
        if not row or not row[0].strip():
            continue
        item = {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        vendedor = str(item.get("vendedor", "")).strip()
        if not vendedor or vendedor.upper() == "TOTAL":
            continue
        cobranza = siscor_db._to_numeric_amount([item.get("comision cobranza", 0)]).iloc[0]
        ventas = siscor_db._to_numeric_amount([item.get("comision ventas", 0)]).iloc[0]
        parsed_rows.append(
            {
                "vendedor": vendedor,
                "comision_cobranza": float(cobranza),
                "comision_ventas": float(ventas),
                "ventas_acumuladas": float(cobranza + ventas),
            }
        )
    return pd.DataFrame(parsed_rows)


def _decrypt_file(path: Path) -> bytes:
    if Fernet is None:
        raise RuntimeError("Falta cryptography para leer comisiones cifradas.")
    key = siscor_db._snapshot_key()
    if not key:
        raise RuntimeError("Falta la clave snapshot para leer comisiones cifradas.")
    try:
        return Fernet(key.encode("utf-8")).decrypt(path.read_bytes())
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("No pude descifrar el archivo de comisiones.") from exc


def _latest_file() -> Path | None:
    if not COMMISSIONS_DIR.exists():
        return None
    files = [*COMMISSIONS_DIR.glob("*.xlsx.enc"), *COMMISSIONS_DIR.glob("*.xlsx")]
    if not files:
        return None
    return max(files, key=_commission_file_sort_key)


def _commission_file_sort_key(path: Path) -> tuple[str, float]:
    match = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{8}_\d{6})", path.name)
    if match:
        return (match.group(1) + "_" + match.group(2), path.stat().st_mtime)
    return ("", path.stat().st_mtime)


def load_latest() -> CommissionResult:
    path = _latest_file()
    if path is None:
        return CommissionResult(
            False,
            "No hay archivo de comisiones cargado.",
            "",
            pd.DataFrame(columns=["vendedor", "comision_cobranza", "comision_ventas", "ventas_acumuladas"]),
        )
    try:
        content = _decrypt_file(path) if path.suffix == ".enc" else path.read_bytes()
        data = _read_xlsx_bytes(content)
        return CommissionResult(True, "OK", path.name, data)
    except Exception as exc:
        return CommissionResult(False, str(exc), path.name, pd.DataFrame())
