from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet


DATA_DIR = Path("data")
FILES = (
    "facturas.csv",
    "factura_items.csv",
    "pedido_items.csv",
    "clientes.csv",
    "creditos.csv",
    "objetivos.csv",
    "parrilla_objetivos.csv",
)
KEY_PATH = DATA_DIR / "snapshot.key"


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    key = KEY_PATH.read_bytes().strip() if KEY_PATH.exists() else Fernet.generate_key()
    cipher = Fernet(key)

    for filename in FILES:
        source = DATA_DIR / filename
        if not source.exists():
            raise FileNotFoundError(f"No se encontro {source}")
        encrypted = cipher.encrypt(source.read_bytes())
        (DATA_DIR / f"{filename}.enc").write_bytes(encrypted)

    KEY_PATH.write_bytes(key)
    print(f"Clave generada en {KEY_PATH}")
    print(key.decode("utf-8"))


if __name__ == "__main__":
    main()
