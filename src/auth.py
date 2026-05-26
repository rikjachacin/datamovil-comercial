from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import base64
import hashlib
import hmac
import os
import time
import tomllib

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


USERS_PATH = Path(".streamlit/users.toml")
SESSION_COOKIE_NAME = "bruncas_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


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


def get_user(username: str) -> User | None:
    normalized_username = username.strip().lower()
    raw_user = load_users().get(normalized_username)
    if not raw_user:
        return None

    zones = tuple(str(zone) for zone in raw_user.get("zones", ()))
    return User(
        username=normalized_username,
        name=str(raw_user.get("name") or normalized_username),
        role=str(raw_user.get("role") or "seller").lower(),
        zones=zones,
    )


def _session_secret() -> str:
    try:
        value = st.secrets.get("auth", {}).get("session_secret")
        if value:
            return str(value)
    except StreamlitSecretNotFoundError:
        pass
    try:
        value = st.secrets.get("data", {}).get("snapshot_key")
        if value:
            return str(value)
    except StreamlitSecretNotFoundError:
        pass
    env_value = os.environ.get("BRUNCAS_SESSION_SECRET")
    if env_value:
        return env_value
    return "bruncas-comercial-local-session"


def _sign(payload: str) -> str:
    digest = hmac.new(
        _session_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def create_session_token(user: User) -> str:
    expires_at = int(time.time()) + SESSION_MAX_AGE_SECONDS
    payload = f"{user.username}|{expires_at}"
    signature = _sign(payload)
    token = f"{payload}|{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def user_from_session_token(token: str | None) -> User | None:
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, raw_expires_at, signature = decoded.split("|", 2)
        payload = f"{username}|{raw_expires_at}"
        if not hmac.compare_digest(signature, _sign(payload)):
            return None
        if int(raw_expires_at) < int(time.time()):
            return None
    except Exception:
        return None
    return get_user(username)
