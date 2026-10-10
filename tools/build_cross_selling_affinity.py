from __future__ import annotations

from io import StringIO
from pathlib import Path
import sys

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import siscor_db


def main() -> None:
    fecha_hasta = sys.argv[1] if len(sys.argv) > 1 else "2026-10-10"
    affinity = siscor_db._cross_selling_affinity(fecha_hasta, recalcular=True)
    if affinity.empty:
        raise RuntimeError("No se pudo calcular la matriz de afinidad.")

    key = siscor_db._snapshot_key()
    if not key:
        raise RuntimeError("No se encontro la clave local de cifrado.")

    buffer = StringIO()
    affinity.to_csv(buffer, index=False)
    encrypted = Fernet(key.encode("utf-8")).encrypt(buffer.getvalue().encode("utf-8"))
    siscor_db.CROSS_SELLING_AFFINITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    siscor_db.CROSS_SELLING_AFFINITY_PATH.write_bytes(encrypted)
    print(f"{siscor_db.CROSS_SELLING_AFFINITY_PATH}: {len(affinity)} relaciones al {fecha_hasta}")


if __name__ == "__main__":
    main()
