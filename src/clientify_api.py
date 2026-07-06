from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, time
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
INBOX_API_BASE_URL = "https://api.clientify.com/team-inbox/api"
CLIENTIFY_PLUS_BASE_URL = "https://plus.clientify.com/team-inbox/api/metrics"
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
class ClientifyActivity:
    enabled: bool
    message: str
    summary: dict[str, Any]
    by_day: list[dict[str, Any]]
    by_channel: list[dict[str, Any]]


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
    token = os.getenv("CLIENTIFY_INBOX_BEARER_TOKEN")
    if token:
        return token.strip()

    try:
        token = st.secrets.get("clientify", {}).get("inbox_bearer_token")
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
        raise RuntimeError(f"Clientify respondio error HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("No se pudo conectar con Clientify.") from exc
    return json.loads(payload.decode("utf-8"))


def _request_inbox_json(path: str, params: dict[str, object] | None = None) -> dict[str, Any]:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("Falta configurar la API key de Clientify.")

    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{INBOX_API_BASE_URL}/{path.lstrip('/')}{query}",
        headers={
            "Authorization": f"Token {api_key}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
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


def _request_metric_json(path: str, params: dict[str, object] | None = None) -> dict[str, Any]:
    token = _inbox_bearer_token()
    if not token:
        raise RuntimeError(
            "Clientify no tiene configurada la credencial del Inbox para metricas exactas. "
            "No se muestran datos parciales para evitar diferencias con Clientify."
        )

    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{CLIENTIFY_PLUS_BASE_URL}/{path.lstrip('/')}{query}",
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
        raise RuntimeError(f"Clientify respondio error HTTP {exc.code} en metricas exactas.") from exc
    except URLError as exc:
        raise RuntimeError("No se pudo conectar con las metricas exactas de Clientify.") from exc
    return json.loads(payload.decode("utf-8"))


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _owner_name(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict):
        return "Sin asignar"
    return str(value.get("full_name") or value.get("username") or "Sin asignar").strip() or "Sin asignar"


def _contact_name(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict):
        return "Sin contacto"
    name = " ".join(
        part.strip()
        for part in (str(value.get("first_name") or ""), str(value.get("last_name") or ""))
        if part and part.strip()
    ).strip()
    return name or str(value.get("id") or "Sin contacto")


def _normalize_text(value: object) -> str:
    text = str(value or "").upper()
    replacements = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ñ": "N",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _owner_matches_zones(owner: str, zones: tuple[str, ...]) -> bool:
    if not zones:
        return True
    owner_norm = _normalize_text(owner)
    zone_aliases = {
        "DAVID": ("DAVID",),
        "NOELIA": ("NOELIA",),
        "MICAELA": ("MICAELA",),
        "MICAELA GONZALEZ": ("MICAELA",),
        "MACA": ("MACA", "MACARENA", "PROTTO"),
        "MACA PROTTO": ("MACA", "MACARENA", "PROTTO"),
        "MACARENA": ("MACA", "MACARENA", "PROTTO"),
        "LUCIA": ("LUCIA",),
        "LUCIA MORENO": ("LUCIA",),
    }
    for zone in zones:
        zone_norm = _normalize_text(zone)
        aliases = zone_aliases.get(zone_norm, (zone_norm,))
        if any(alias and alias in owner_norm for alias in aliases):
            return True
    return False


def _message_direction(message: dict[str, Any]) -> str:
    msg_type = str(message.get("type") or "").lower()
    if msg_type == "incoming" or message.get("sent_by_company") is False:
        return "recibido"
    return "enviado"


@st.cache_data(ttl=300, show_spinner=False)
def inbox_activity(fecha_desde_sql: str, fecha_hasta_sql: str, zones: tuple[str, ...] = ()) -> ClientifyActivity:
    try:
        start_date = datetime.fromisoformat(fecha_desde_sql).date()
        end_date = datetime.fromisoformat(fecha_hasta_sql).date()
    except ValueError:
        return ClientifyActivity(False, "Rango de fechas invalido para Clientify.", {}, [], [])

    metric_params = {
        "date_start": fecha_desde_sql,
        "date_end": fecha_hasta_sql,
        "time_zone": "America/Buenos_Aires",
        "compare_with_previous": "true",
    }
    try:
        summary_data = _request_metric_json("dashboard/summary/", metric_params)
        daily_data = _request_metric_json("dashboard/timeseries/", {**metric_params, "series": "daily"})
    except Exception as exc:
        return ClientifyActivity(False, str(exc), {}, [], [])

    current = summary_data.get("current") if isinstance(summary_data.get("current"), dict) else summary_data
    total_days = max((end_date - start_date).days + 1, 1)
    total_conversations = int(current.get("total_conversations") or 0)

    summary = {
        "conversaciones": total_conversations,
        "promedio_diario": total_conversations / total_days,
        "dias_periodo": total_days,
        "canal": "Todos",
    }

    daily_rows = daily_data.get("buckets") or daily_data.get("items") or daily_data.get("series") or []
    by_day = []
    for row in daily_rows:
        if not isinstance(row, dict):
            continue
        day = row.get("day") or row.get("date")
        if not day:
            continue
        by_day.append({"fecha": str(day), "conversaciones": int(row.get("count") or row.get("value") or 0)})

    return ClientifyActivity(
        True,
        "OK" if total_conversations else "No hay conversaciones de Clientify en el periodo seleccionado.",
        summary,
        sorted(by_day, key=lambda row: row["fecha"]),
        [],
    )


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
