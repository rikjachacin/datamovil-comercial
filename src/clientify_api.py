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
    by_owner: list[dict[str, Any]]
    detail: list[dict[str, Any]]


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
    if not _api_key():
        return ClientifyActivity(False, "Falta configurar la API key de Clientify.", {}, [], [], [])

    try:
        start_date = datetime.fromisoformat(fecha_desde_sql).date()
        end_date = datetime.fromisoformat(fecha_hasta_sql).date()
    except ValueError:
        return ClientifyActivity(False, "Rango de fechas invalido para Clientify.", {}, [], [], [])

    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    conversations: list[dict[str, Any]] = []

    try:
        for page in range(1, 11):
            data = _request_inbox_json(
                "conversations/",
                {
                    "page_size": 200,
                    "page": page,
                    "last_interaction__date__gte": fecha_desde_sql,
                    "last_interaction__date__lte": fecha_hasta_sql,
                },
            )
            rows = data.get("results") or []
            if not isinstance(rows, list) or not rows:
                break
            stop_after_page = False
            for row in rows:
                last_dt = _parse_dt(row.get("last_interaction") or row.get("created"))
                if not last_dt:
                    continue
                naive_last = last_dt.replace(tzinfo=None)
                if naive_last < start_dt:
                    stop_after_page = True
                    continue
                conversations.append(row)
            if stop_after_page or not data.get("next"):
                break
    except Exception as exc:
        return ClientifyActivity(False, str(exc), {}, [], [], [])

    detail: list[dict[str, Any]] = []

    for conversation in conversations:
        owner = _owner_name(conversation.get("owner"))
        if not _owner_matches_zones(owner, zones):
            continue
        conv_id = conversation.get("id")
        if not conv_id:
            continue
        last_dt = _parse_dt(conversation.get("last_interaction") or conversation.get("created"))
        if not last_dt:
            continue
        naive_last = last_dt.replace(tzinfo=None)
        if not (start_dt <= naive_last <= end_dt):
            continue

        contact = _contact_name(conversation.get("contact"))
        status = str(conversation.get("status") or "sin estado").lower()
        last_message = conversation.get("last_message") if isinstance(conversation.get("last_message"), dict) else {}
        direction = _message_direction(last_message)
        detail.append(
            {
                "fecha_hora": last_dt.isoformat(),
                "fecha": last_dt.date().isoformat(),
                "hora": last_dt.hour,
                "vendedor": owner,
                "cliente": contact,
                "estado": status,
                "ultimo_mensaje": direction,
                "canal": str(conversation.get("channel_type") or "").title(),
                "conversacion_id": conv_id,
            }
        )

    open_count = sum(1 for row in detail if row["estado"] == "open")
    closed_count = sum(1 for row in detail if row["estado"] == "closed")
    frozen_count = sum(1 for row in detail if row["estado"] == "frozen")
    owners = sorted({row["vendedor"] for row in detail})
    summary = {
        "conversaciones": len(detail),
        "abiertas": open_count,
        "cerradas": closed_count,
        "congeladas": frozen_count,
        "vendedores": len(owners),
    }

    by_day_map: dict[str, dict[str, Any]] = {}
    by_owner_map: dict[str, dict[str, Any]] = {}
    for row in detail:
        day = row["fecha"]
        day_bucket = by_day_map.setdefault(day, {"fecha": day, "conversaciones": 0, "abiertas": 0, "cerradas": 0})
        day_bucket["conversaciones"] += 1
        if row["estado"] == "open":
            day_bucket["abiertas"] += 1
        elif row["estado"] == "closed":
            day_bucket["cerradas"] += 1

        owner = row["vendedor"]
        owner_bucket = by_owner_map.setdefault(
            owner,
            {"vendedor": owner, "conversaciones": 0, "abiertas": 0, "cerradas": 0},
        )
        owner_bucket["conversaciones"] += 1
        if row["estado"] == "open":
            owner_bucket["abiertas"] += 1
        elif row["estado"] == "closed":
            owner_bucket["cerradas"] += 1

    return ClientifyActivity(
        True,
        "OK" if detail else "No hay conversaciones de Clientify en el periodo seleccionado.",
        summary,
        sorted(by_day_map.values(), key=lambda row: row["fecha"]),
        sorted(by_owner_map.values(), key=lambda row: row["conversaciones"], reverse=True),
        sorted(detail, key=lambda row: row["fecha_hora"], reverse=True),
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
