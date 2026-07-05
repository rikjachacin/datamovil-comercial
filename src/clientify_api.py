from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from src import siscor_db

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = ValueError


API_BASE_URL = "https://api.clientify.com/v1"
ENCRYPTED_KEY_PATH = Path("data/clientify_api_key.enc")
REQUEST_TIMEOUT_SECONDS = 25

CONVERSATIONS_REPORT = {
    "type": "rendimiento_conversaciones",
    "pageid": "LocUj5KQw6BKwhS9jIwd1",
    "clientid": "vi@sample.com",
    "dataset_id": "eajp0ke8l,abuyjwfuu",
    "permission": "Communication Reports",
}


@dataclass(frozen=True)
class QrveyReport:
    enabled: bool
    message: str
    token: str = ""
    widget_url: str = ""


def _api_key() -> str | None:
    env_key = os.getenv("CLIENTIFY_API_KEY")
    if env_key:
        return env_key.strip()

    try:
        key = st.secrets.get("clientify", {}).get("api_key")
        if key:
            return str(key).strip()
    except StreamlitSecretNotFoundError:
        pass

    if not ENCRYPTED_KEY_PATH.exists() or Fernet is None:
        return None

    key = siscor_db._snapshot_key()
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8")).decrypt(ENCRYPTED_KEY_PATH.read_bytes()).decode("utf-8").strip()
    except (InvalidToken, ValueError):
        return None


def _request_json(path: str, params: dict[str, object] | None = None) -> dict[str, Any]:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("Falta configurar la API key de Clientify.")

    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{API_BASE_URL}/{path.lstrip('/')}{query}",
        headers={"Authorization": f"Token {api_key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Clientify respondio error HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("No se pudo conectar con Clientify.") from exc
    return json.loads(payload.decode("utf-8"))


@st.cache_data(ttl=300, show_spinner=False)
def conversations_report() -> QrveyReport:
    if not _api_key():
        return QrveyReport(False, "Falta configurar la API key de Clientify.")

    try:
        data = _request_json(
            "qrveys/auth",
            {
                "pageid": CONVERSATIONS_REPORT["pageid"],
                "clientid": CONVERSATIONS_REPORT["clientid"],
                "datasetid": CONVERSATIONS_REPORT["dataset_id"],
                "type": CONVERSATIONS_REPORT["type"],
            },
        )
    except Exception as exc:
        return QrveyReport(False, str(exc))

    token = str(data.get("token") or "").strip()
    widget_url = str(data.get("widgetUrl") or "").strip()
    if not token or not widget_url:
        return QrveyReport(False, "Clientify no devolvio token o widgetUrl para el reporte.")
    return QrveyReport(True, "OK", token=token, widget_url=widget_url)
