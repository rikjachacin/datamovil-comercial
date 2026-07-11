from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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
    by_owner: list[dict[str, Any]]


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


LOCAL_TIMEZONE = ZoneInfo("America/Buenos_Aires")


def _local_dt(value: object) -> datetime | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=LOCAL_TIMEZONE)
    return parsed.astimezone(LOCAL_TIMEZONE)


def _owner_id(value: object) -> int | None:
    if isinstance(value, dict):
        value = value.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_text_message(message: dict[str, Any]) -> bool:
    message_type = str(message.get("type") or "").lower()
    text = str(message.get("text") or "").strip()
    return (
        message_type in {"incoming", "outgoing"}
        and bool(text)
        and not message.get("media")
        and not message.get("sent_by_bot")
    )


def _fetch_conversation_pages(start_dt: datetime, end_dt: datetime) -> list[dict[str, Any]]:
    conversations: dict[int, dict[str, Any]] = {}
    for first_page in range(1, 51, 5):
        batch_dates: list[datetime] = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(
                    _request_inbox_json,
                    "conversations/",
                    {"page": page, "page_size": 100},
                )
                for page in range(first_page, first_page + 5)
            ]
            for future in as_completed(futures):
                payload = future.result()
                rows = payload.get("results") or []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    conversation_id = row.get("id")
                    if isinstance(conversation_id, int):
                        conversations[conversation_id] = row
                    interaction_dt = _local_dt(row.get("last_interaction"))
                    if interaction_dt:
                        batch_dates.append(interaction_dt)
        if batch_dates and max(batch_dates) < start_dt:
            break

    return [
        row
        for row in conversations.values()
        if str(row.get("channel_type") or "").lower() == "whatsapp"
        and (interaction_dt := _local_dt(row.get("last_interaction"))) is not None
        and interaction_dt >= start_dt
    ]


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_messages_in_period(
    conversation_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for page in range(1, 51):
        payload = _request_inbox_json(
            f"conversations/{conversation_id}/messages/",
            {"page": page, "page_size": 100},
        )
        rows = [row for row in (payload.get("results") or []) if isinstance(row, dict)]
        if not rows:
            break
        page_dates: list[datetime] = []
        for message in rows:
            created_dt = _local_dt(message.get("created"))
            if not created_dt:
                continue
            page_dates.append(created_dt)
            if start_dt <= created_dt <= end_dt and _is_text_message(message):
                selected.append(message)
        if page_dates and max(page_dates) < start_dt:
            break
        if not payload.get("next"):
            break
    return selected


@st.cache_data(ttl=300, show_spinner=False)
def inbox_activity(fecha_desde_sql: str, fecha_hasta_sql: str, zones: tuple[str, ...] = ()) -> ClientifyActivity:
    try:
        start_date = datetime.fromisoformat(fecha_desde_sql).date()
        end_date = datetime.fromisoformat(fecha_hasta_sql).date()
    except ValueError:
        return ClientifyActivity(False, "Rango de fechas invalido para Clientify.", {}, [], [])

    total_days = max((end_date - start_date).days + 1, 1)
    start_dt = datetime.combine(start_date, time.min, tzinfo=LOCAL_TIMEZONE)
    end_dt = datetime.combine(end_date, time.max, tzinfo=LOCAL_TIMEZONE)
    try:
        candidates = [
            row
            for row in _fetch_conversation_pages(start_dt, end_dt)
            if _owner_matches_zones(_owner_name(row.get("owner")), zones)
        ]
        messages_by_conversation: dict[int, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=40) as executor:
            futures = {
                executor.submit(_fetch_messages_in_period, row["id"], start_dt, end_dt): row
                for row in candidates
            }
            for future in as_completed(futures):
                row = futures[future]
                messages_by_conversation[row["id"]] = future.result()
    except Exception as exc:
        return ClientifyActivity(False, str(exc), {}, [], [])

    active_conversations: set[int] = set()
    unique_contacts: set[str] = set()
    by_day_map: dict[str, set[int]] = {}
    by_owner_map: dict[str, dict[str, Any]] = {}
    total_text_messages = 0
    for row in candidates:
        conversation_id = row["id"]
        messages = messages_by_conversation.get(conversation_id, [])
        if not messages:
            continue
        owner = _owner_name(row.get("owner"))
        contact = row.get("contact") if isinstance(row.get("contact"), dict) else {}
        contact_key = str(contact.get("id") or row.get("source_id") or conversation_id)
        active_conversations.add(conversation_id)
        unique_contacts.add(contact_key)
        total_text_messages += len(messages)
        owner_row = by_owner_map.setdefault(
            owner,
            {"telemarketer": owner, "conversaciones": set(), "clientes": set(), "mensajes_texto": 0},
        )
        owner_row["conversaciones"].add(conversation_id)
        owner_row["clientes"].add(contact_key)
        owner_row["mensajes_texto"] += len(messages)
        for message in messages:
            created_dt = _local_dt(message.get("created"))
            if created_dt:
                by_day_map.setdefault(created_dt.date().isoformat(), set()).add(conversation_id)

    total_conversations = len(active_conversations)
    by_day = [
        {"fecha": day, "conversaciones": len(conversation_ids)}
        for day, conversation_ids in by_day_map.items()
    ]
    by_owner = [
        {
            "telemarketer": row["telemarketer"],
            "conversaciones": len(row["conversaciones"]),
            "clientes": len(row["clientes"]),
            "mensajes_texto": row["mensajes_texto"],
        }
        for row in by_owner_map.values()
    ]

    return ClientifyActivity(
        True,
        "OK" if total_conversations else "No hay conversaciones de Clientify en el periodo seleccionado.",
        {
            "conversaciones": total_conversations,
            "clientes": len(unique_contacts),
            "mensajes_texto": total_text_messages,
            "dias_periodo": total_days,
            "fuente": "api_publica_whatsapp",
        },
        sorted(by_day, key=lambda row: row["fecha"]),
        sorted(by_owner, key=lambda row: (-row["conversaciones"], row["telemarketer"])),
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
