from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hmac
import tomllib

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


USERS_PATH = Path(".streamlit/users.toml")


@dataclass(frozen=True)
class User:
    username: str
    name: str
    role: str
    zones: tuple[str, ...]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin" or "*" in self.zones


def load_users(path: Path = USERS_PATH) -> dict[str, dict[str, object]]:
    try:
        if "users" in st.secrets:
            return {key.lower(): dict(value) for key, value in st.secrets["users"].items()}
    except StreamlitSecretNotFoundError:
        pass

    if not path.exists():
        raise RuntimeError(f"No se encontro el archivo de usuarios: {path}")
    with path.open("rb") as file:
        data = tomllib.load(file)
    return data.get("users", {})


def authenticate(username: str, password: str) -> User | None:
    normalized_username = username.strip().lower()
    users = load_users()
    raw_user = users.get(normalized_username)
    if not raw_user:
        return None

    stored_password = str(raw_user.get("password", ""))
    if not hmac.compare_digest(stored_password, password):
        return None

    zones = tuple(str(zone) for zone in raw_user.get("zones", ()))
    return User(
        username=normalized_username,
        name=str(raw_user.get("name") or normalized_username),
        role=str(raw_user.get("role") or "seller").lower(),
        zones=zones,
    )
