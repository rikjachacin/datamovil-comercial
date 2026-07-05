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
import pandas as pd

from src import siscor_db

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = ValueError


API_BASE_URL = "https://api.clientify.com/v1"
CLIENTIFY_INBOX_REPORT_URL = "https://new.clientify.com/reports/inbox"
INBOX_API_BASE_URL = "https://plus.clientify.com/team-inbox/api/metrics"
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


@dataclass(frozen=True)
class InboxMetrics:
    enabled: bool
    message: str
    summary: dict[str, Any]
    daily: pd.DataFrame
    agents: pd.DataFrame


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


def _inbox_bearer_token() -> str | None:
    env_token = os.getenv("CLIENTIFY_INBOX_BEARER_TOKEN")
    if env_token:
        return env_token.strip()

    try:
        secrets_value = st.secrets.get("clientify", {})
        token = secrets_value.get("inbox_bearer_token") or secrets_value.get("bearer_token")
        if token:
            return str(token).strip()
    except StreamlitSecretNotFoundError:
        pass
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
        if path.lstrip("/") == "qrveys/auth" and exc.code >= 500:
            raise RuntimeError(
                "Clientify tiene caido el reporte embebido de conversaciones "
                "(HTTP 500). La API key esta cargada y responde en otros modulos, "
                "pero este reporte depende de un servicio interno de Clientify."
            ) from exc
        raise RuntimeError(f"Clientify respondio error HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("No se pudo conectar con Clientify.") from exc
    return json.loads(payload.decode("utf-8"))


def _request_inbox_json(path: str, params: dict[str, object] | None = None) -> dict[str, Any]:
    token = _inbox_bearer_token()
    if not token:
        raise RuntimeError(
            "Falta configurar CLIENTIFY_INBOX_BEARER_TOKEN. "
            "La API key publica de Clientify no alcanza para leer las metricas del Inbox."
        )

    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{INBOX_API_BASE_URL}/{path.strip('/')}/{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError(
                "Clientify rechazo el token Bearer del Inbox. "
                "Hace falta un token valido para las metricas internas de conversaciones."
            ) from exc
        raise RuntimeError(f"Clientify Inbox respondio error HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("No se pudo conectar con Clientify Inbox.") from exc
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


@st.cache_data(ttl=300, show_spinner=False)
def inbox_metrics(fecha_desde: str, fecha_hasta: str) -> InboxMetrics:
    params = {
        "date_start": fecha_desde,
        "date_end": fecha_hasta,
        "time_zone": "America/Buenos_Aires",
        "compare_with_previous": "true",
    }

    try:
        summary_data = _request_inbox_json("dashboard/summary", params)
        daily_data = _request_inbox_json("dashboard/timeseries", {**params, "series": "daily"})
        agents_data = _request_inbox_json("agent-performance", params)
    except Exception as exc:
        return InboxMetrics(False, str(exc), {}, pd.DataFrame(), pd.DataFrame())

    current = summary_data.get("current") or summary_data
    daily_rows = (
        daily_data.get("buckets")
        or daily_data.get("items")
        or daily_data.get("series")
        or daily_data.get("results")
        or []
    )
    agents_rows = agents_data.get("agents") or agents_data.get("results") or agents_data.get("items") or []

    daily = pd.DataFrame(daily_rows)
    if not daily.empty:
        if "day" not in daily.columns and "date" in daily.columns:
            daily["day"] = daily["date"]
        if "new_conversations" not in daily.columns:
            count_col = "count" if "count" in daily.columns else "value" if "value" in daily.columns else None
            daily["new_conversations"] = pd.to_numeric(daily[count_col], errors="coerce").fillna(0) if count_col else 0
        daily["day"] = pd.to_datetime(daily["day"], errors="coerce")
        daily["new_conversations"] = pd.to_numeric(daily["new_conversations"], errors="coerce").fillna(0)
        daily = daily.dropna(subset=["day"]).sort_values("day")

    agents = pd.DataFrame(agents_rows)
    return InboxMetrics(True, "OK", current, daily, agents)
