from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src import siscor_db


OUTPUT_DIR = PROJECT_ROOT / "data"


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    facturas = siscor_db.export_facturas_snapshot()
    factura_items = siscor_db.export_factura_items_snapshot()

    facturas.to_csv(OUTPUT_DIR / "facturas.csv", index=False, encoding="utf-8-sig")
    factura_items.to_csv(OUTPUT_DIR / "factura_items.csv", index=False, encoding="utf-8-sig")

    print(f"facturas.csv: {len(facturas):,} filas")
    print(f"factura_items.csv: {len(factura_items):,} filas")


if __name__ == "__main__":
    main()
