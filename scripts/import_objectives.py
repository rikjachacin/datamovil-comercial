from __future__ import annotations

from pathlib import Path

import pandas as pd


SOURCE_PATH = Path(r"C:\Users\Usuario\Downloads\Objtivos de vendedores.csv")
OUTPUT_PATH = Path("data/objetivos.csv")
DEFAULT_MONTH = "2026-05"
ZONE_MAP = {
    "JAVIER": "ZONA 13 JAVIER MOLARO",
}


def parse_money(value: object) -> float:
    text = str(value).replace("$", "").replace(".", "").replace(",", ".").strip()
    return float(text) if text else 0.0


def main() -> None:
    df = pd.read_csv(SOURCE_PATH, sep=";")
    out = pd.DataFrame(
        {
            "mes": DEFAULT_MONTH,
            "zona": df["Vendedor"].astype(str).str.strip().replace(ZONE_MAP),
            "objetivo": df["Objetivo"].map(parse_money),
        }
    )
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)
    print(f"{OUTPUT_PATH}: {len(out):,} objetivos")


if __name__ == "__main__":
    main()
