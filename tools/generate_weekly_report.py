from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import weekly_reports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el informe semanal de vendedores.")
    parser.add_argument("--fecha", help="Fecha de corte YYYY-MM-DD; por defecto usa hoy.")
    parser.add_argument("--desde", help="Inicio de actividad YYYY-MM-DD; por defecto usa el lunes.")
    args = parser.parse_args()
    cutoff = date.fromisoformat(args.fecha) if args.fecha else date.today()
    period_start = date.fromisoformat(args.desde) if args.desde else None
    result = weekly_reports.generate_report(cutoff, period_start=period_start)
    if not result.enabled:
        print(f"ERROR: {result.message}", file=sys.stderr)
        return 1
    print(result.path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
