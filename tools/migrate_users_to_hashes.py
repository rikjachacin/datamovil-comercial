from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auth import password_hash


USERS_PATH = Path(".streamlit/users.toml")


def main() -> int:
    if not USERS_PATH.exists():
        print(f"No existe {USERS_PATH}")
        return 1

    text = USERS_PATH.read_text(encoding="utf-8")

    def replace_password(match: re.Match[str]) -> str:
        password = match.group("password")
        return f'password_hash = "{password_hash(password)}"'

    updated = re.sub(
        r'^password\s*=\s*"(?P<password>[^"]*)"\s*$',
        replace_password,
        text,
        flags=re.MULTILINE,
    )
    if updated == text:
        print("No encontre contrasenas en texto plano para migrar.")
        return 0

    backup_path = USERS_PATH.with_suffix(".toml.bak")
    backup_path.write_text(text, encoding="utf-8")
    USERS_PATH.write_text(updated, encoding="utf-8")
    print(f"Migrado. Respaldo creado en {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
