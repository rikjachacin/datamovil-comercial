from __future__ import annotations

from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd


DATA_DIR = Path("data")
OUTPUT_PATH = DATA_DIR / "parrilla_objetivos.csv"
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _shared_strings(zip_file: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.findall(".//x:t", NS)) for item in root.findall("x:si", NS)]


def _col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for char in letters:
        value = value * 26 + ord(char.upper()) - 64
    return max(value - 1, 0)


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    value = cell.find("x:v", NS)
    if value is None:
        return ""
    raw = value.text or ""
    if cell.attrib.get("t") == "s" and raw.isdigit():
        index = int(raw)
        return shared[index] if index < len(shared) else raw
    return raw


def read_first_sheet(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as zip_file:
        shared = _shared_strings(zip_file)
        root = ET.fromstring(zip_file.read("xl/worksheets/sheet1.xml"))
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


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Uso: python tools/import_parrilla_objectives.py objetivos.xlsx [YYYY-MM]")

    source = Path(sys.argv[1])
    month = sys.argv[2] if len(sys.argv) == 3 else "2026-06"
    if not source.exists():
        raise FileNotFoundError(f"No se encontro {source}")

    rows = read_first_sheet(source)
    if not rows:
        raise ValueError("El archivo no tiene filas.")

    headers = [str(value).strip() for value in rows[0]]
    if not headers or headers[0].strip().lower() != "laboratorio":
        raise ValueError("La primera columna debe ser Laboratorio.")

    records: list[dict[str, object]] = []
    for row in rows[1:]:
        if not row or not str(row[0]).strip():
            continue
        laboratory = str(row[0]).strip()
        for index, seller in enumerate(headers[1:], start=1):
            seller = str(seller).strip()
            if not seller:
                continue
            raw_goal = row[index] if index < len(row) else ""
            records.append(
                {
                    "mes": month,
                    "laboratorio": laboratory,
                    "vendedor": seller,
                    "objetivo": pd.to_numeric(raw_goal, errors="coerce"),
                }
            )

    DATA_DIR.mkdir(exist_ok=True)
    pd.DataFrame(records).to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    print(f"{OUTPUT_PATH}: {len(records)} objetivos")


if __name__ == "__main__":
    main()
