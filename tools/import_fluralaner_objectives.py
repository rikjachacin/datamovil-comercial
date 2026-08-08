from __future__ import annotations

from io import StringIO
from pathlib import Path
import sys

import pandas as pd
from cryptography.fernet import Fernet


DATA_DIR = Path("data")
KEY_PATH = DATA_DIR / "snapshot.key"
OUTPUT_PATH = DATA_DIR / "fluralaner_objetivos.csv.enc"
PRODUCTS = ("Feline Full", "Bit Trio", "Ectholaner", "Zanex")
ZONE_ALIASES = {
    "JULIO MARTINEZ": "JONATAN MERCAO",
}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python tools/import_fluralaner_objectives.py objetivos.xlsx")

    source = Path(sys.argv[1])
    if not source.exists():
        raise FileNotFoundError(f"No se encontro {source}")
    if source.suffix.lower() != ".xlsx":
        raise ValueError("El archivo debe ser .xlsx")
    if not KEY_PATH.exists():
        raise RuntimeError("Falta data/snapshot.key para cifrar los objetivos.")

    raw = pd.read_excel(source, sheet_name=0, header=1)
    raw.columns = [str(column).strip() for column in raw.columns]
    if not len(raw.columns):
        raise ValueError("El archivo no tiene columnas.")
    raw = raw.rename(columns={raw.columns[0]: "zona"})
    missing = [column for column in ("zona", *PRODUCTS) if column not in raw.columns]
    if missing:
        raise ValueError(f"Faltan columnas: {', '.join(missing)}")

    raw = raw.loc[:, ["zona", *PRODUCTS]].copy()
    raw["zona"] = raw["zona"].fillna("").astype(str).str.strip().str.upper().replace(ZONE_ALIASES)
    raw = raw[raw["zona"].ne("")].copy()
    if raw["zona"].duplicated().any():
        duplicates = ", ".join(raw.loc[raw["zona"].duplicated(), "zona"].unique())
        raise ValueError(f"Hay vendedores duplicados: {duplicates}")

    records = raw.melt(id_vars="zona", var_name="producto", value_name="objetivo")
    records["objetivo"] = pd.to_numeric(records["objetivo"], errors="coerce")
    if records["objetivo"].isna().any():
        invalid = records[records["objetivo"].isna()].loc[:, ["zona", "producto"]]
        raise ValueError(f"Hay objetivos no numericos:\n{invalid.to_string(index=False)}")
    if records["objetivo"].lt(0).any():
        raise ValueError("Los objetivos no pueden ser negativos.")
    records["objetivo"] = records["objetivo"].astype(float)
    records = records.loc[:, ["zona", "producto", "objetivo"]]

    csv_buffer = StringIO()
    records.to_csv(csv_buffer, index=False, lineterminator="\n")
    key = KEY_PATH.read_bytes().strip()
    encrypted = Fernet(key).encrypt(csv_buffer.getvalue().encode("utf-8"))
    OUTPUT_PATH.write_bytes(encrypted)

    totals = records.groupby("producto", sort=False)["objetivo"].sum()
    print(f"{OUTPUT_PATH}: {len(records)} objetivos, {len(raw)} zonas")
    for product in PRODUCTS:
        print(f"{product}: {totals.get(product, 0):.0f}")


if __name__ == "__main__":
    main()
