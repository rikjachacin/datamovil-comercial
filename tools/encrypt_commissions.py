from __future__ import annotations

from pathlib import Path
import sys

from cryptography.fernet import Fernet


DATA_DIR = Path("data")
COMMISSIONS_DIR = DATA_DIR / "comisiones"
KEY_PATH = DATA_DIR / "snapshot.key"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python tools/encrypt_commissions.py ruta_al_excel.xlsx")

    source = Path(sys.argv[1])
    if not source.exists():
        raise FileNotFoundError(f"No se encontro {source}")
    if source.suffix.lower() != ".xlsx":
        raise ValueError("El archivo debe ser .xlsx")

    COMMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    key = KEY_PATH.read_bytes().strip() if KEY_PATH.exists() else Fernet.generate_key()
    cipher = Fernet(key)
    target = COMMISSIONS_DIR / f"{source.stem}.xlsx.enc"
    target.write_bytes(cipher.encrypt(source.read_bytes()))
    KEY_PATH.write_bytes(key)
    print(target)


if __name__ == "__main__":
    main()
