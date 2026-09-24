from __future__ import annotations

from io import StringIO
from pathlib import Path
import sys

import pandas as pd
from cryptography.fernet import Fernet
from openpyxl import load_workbook


OUTPUT_PATH = Path("data/cross_selling_rules.csv.enc")
KEY_PATH = Path("data/snapshot.key")
SHEET_NAME = "Cruces sugeridos"
ALLOWED_DECISIONS = {
    "Piloto prioritario",
    "Piloto supervisado",
    "Piloto segmentado",
}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python tools/import_cross_selling_rules.py reglas.xlsx")

    source = Path(sys.argv[1])
    if not source.exists():
        raise FileNotFoundError(f"No se encontro {source}")
    if not KEY_PATH.exists():
        raise FileNotFoundError("No se encontro data/snapshot.key")

    workbook = load_workbook(source, read_only=False, data_only=True)
    if SHEET_NAME not in workbook.sheetnames:
        raise ValueError(f"Falta la hoja {SHEET_NAME}")

    sheet = workbook[SHEET_NAME]
    rows = list(sheet.iter_rows(min_row=6, values_only=True))
    records: list[dict[str, object]] = []
    for row in rows:
        if not row or row[0] is None or str(row[4]).strip() not in ALLOWED_DECISIONS:
            continue
        records.append(
            {
                "origen_id": int(row[0]),
                "origen": str(row[1]).strip(),
                "destino_id": int(row[2]),
                "destino": str(row[3]).strip(),
                "decision": str(row[4]).strip(),
                "segmento": str(row[5]).strip(),
                "coincidencia": float(row[8] or 0),
                "sugerencia": str(row[9]).strip(),
                "validacion": str(row[10]).strip(),
            }
        )

    if not records:
        raise ValueError("No se encontraron reglas habilitadas.")

    buffer = StringIO()
    pd.DataFrame(records).to_csv(buffer, index=False)
    encrypted = Fernet(KEY_PATH.read_bytes().strip()).encrypt(buffer.getvalue().encode("utf-8"))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(encrypted)
    print(f"{OUTPUT_PATH}: {len(records)} reglas")


if __name__ == "__main__":
    main()
