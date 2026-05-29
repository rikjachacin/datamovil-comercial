from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import base64
import hashlib
import hmac
import os
import secrets
import time
import tomllib

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


USERS_PATH = Path(".streamlit/users.toml")
SESSION_COOKIE_NAME = "bruncas_session"
SESSION_QUERY_PARAM = "bruncas_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 15 * 60
_RUNTIME_SESSION_SECRET = secrets.token_urlsafe(48)
_LOGIN_ATTEMPTS: dict[str, tuple[int, float]] = {}


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


def password_hash(password: str, salt: str | None = None) -> str:
    raw_salt = salt or secrets.token_urlsafe(24)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        raw_salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    )
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${raw_salt}${encoded_digest}"


def verify_password(password: str, raw_user: dict[str, object]) -> bool:
    stored_hash = str(raw_user.get("password_hash", ""))
    if stored_hash:
        try:
            algorithm, raw_iterations, salt, expected_digest = stored_hash.split("$", 3)
            if algorithm != PASSWORD_HASH_ALGORITHM:
                return False
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                int(raw_iterations),
            )
            actual_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
            return hmac.compare_digest(actual_digest, expected_digest)
        except Exception:
            return False

    # Legacy compatibility: keep plaintext support only to avoid locking existing installs.
    stored_password = str(raw_user.get("password", ""))
    return bool(stored_password) and hmac.compare_digest(stored_password, password)


def login_block_seconds(username: str) -> int:
    normalized_username = username.strip().lower()
    attempts, locked_until = _LOGIN_ATTEMPTS.get(normalized_username, (0, 0))
    if attempts < LOGIN_MAX_ATTEMPTS or locked_until <= time.time():
        return 0
    return max(1, int(locked_until - time.time()))


def register_login_failure(username: str) -> None:
    normalized_username = username.strip().lower()
    attempts, locked_until = _LOGIN_ATTEMPTS.get(normalized_username, (0, 0))
    now = time.time()
    if locked_until <= now:
        attempts += 1
    if attempts >= LOGIN_MAX_ATTEMPTS:
        locked_until = now + LOGIN_LOCK_SECONDS
    _LOGIN_ATTEMPTS[normalized_username] = (attempts, locked_until)


def clear_login_failures(username: str) -> None:
    _LOGIN_ATTEMPTS.pop(username.strip().lower(), None)


def authenticate(username: str, password: str) -> User | None:
    normalized_username = username.strip().lower()
    if login_block_seconds(normalized_username):
        return None

    users = load_users()
    raw_user = users.get(normalized_username)
    if not raw_user:
        register_login_failure(normalized_username)
        return None

    if not verify_password(password, raw_user):
        register_login_failure(normalized_username)
        return None

    clear_login_failures(normalized_username)
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
    return _RUNTIME_SESSION_SECRET


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
