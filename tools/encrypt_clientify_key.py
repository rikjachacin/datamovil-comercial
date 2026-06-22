from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet


DATA_DIR = Path("data")
TARGET = DATA_DIR / "clientify_api_key.enc"


def main() -> None:
    api_key = os.getenv("CLIENTIFY_API_KEY", "").strip()
    snapshot_key = os.getenv("SNAPSHOT_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta CLIENTIFY_API_KEY en variables de entorno.")
    if not snapshot_key:
        key_path = DATA_DIR / "snapshot.key"
        if key_path.exists():
            snapshot_key = key_path.read_text(encoding="utf-8").strip()
    if not snapshot_key:
        raise SystemExit("Falta SNAPSHOT_KEY o data/snapshot.key.")

    DATA_DIR.mkdir(exist_ok=True)
    cipher = Fernet(snapshot_key.encode("utf-8"))
    TARGET.write_bytes(cipher.encrypt(api_key.encode("utf-8")))
    print(f"Clave Clientify cifrada en {TARGET}")


if __name__ == "__main__":
    main()
