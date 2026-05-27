from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auth import password_hash


def main() -> int:
    password = getpass.getpass("Contrasena a proteger: ")
    confirmation = getpass.getpass("Repetir contrasena: ")
    if password != confirmation:
        print("Las contrasenas no coinciden.")
        return 1
    print(password_hash(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
