from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from src import siscor_db

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = ValueError


AUTH_URL = "https://sso.anura.com.ar/auth/realms/anura/protocol/openid-connect/token"
API_BASE_URL = "https://api.anura.com.ar/GCAPI/rest/tenants"
ENCRYPTED_CREDENTIALS_PATH = Path("data/anura_credentials.enc")
REQUEST_TIMEOUT_SECONDS = 25

TELEMARKETING_ACCOUNTS: dict[str, tuple[str, ...]] = {
    "MACA PROTTO": ("100", "MACARENA PROTTO", "MACA PROTTO"),
    "DAVID": ("101", "DAVID"),
    "NOELIA": ("103", "NOELIA"),
    "MICAELA GONZALEZ": ("104", "MICAELA"),
}


@dataclass(frozen=True)
class AnuraResult:
    enabled: bool
    message: str
    calls: pd.DataFrame


def _credentials() -> tuple[str, str] | None:
    env_client_id = os.getenv("ANURA_CLIENT_ID")
    env_client_password = os.getenv("ANURA_CLIENT_PASSWORD")
    if env_client_id and env_client_password:
        return env_client_id.strip(), env_client_password.strip()

    try:
        secrets_value = st.secrets.get("anura", {})
        client_id = secrets_value.get("client_id")
        client_password = secrets_value.get("client_password")
        if client_id and client_password:
            return str(client_id).strip(), str(client_password).strip()
    except StreamlitSecretNotFoundError:
        pass

    if not ENCRYPTED_CREDENTIALS_PATH.exists() or Fernet is None:
        return None

    key = siscor_db._snapshot_key()
    if not key:
        return None
    try:
        raw = Fernet(key.encode("utf-8")).decrypt(ENCRYPTED_CREDENTIALS_PATH.read_bytes())
        data = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return None

    client_id = str(data.get("client_id") or "").strip()
    client_password = str(data.get("client_password") or "").strip()
    if not client_id or not client_password:
        return None
    return client_id, client_password


def _post_form(url: str, body: dict[str, str], client_id: str, client_password: str) -> dict[str, Any]:
    token = base64.b64encode(f"{client_id}:{client_password}".encode("utf-8")).decode("ascii")
    request = Request(
        url,
        data=urlencode(body).encode("utf-8"),
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Anura respondio error HTTP {exc.code} al pedir token.") from exc
    except URLError as exc:
        raise RuntimeError("No se pudo conectar con Anura.") from exc
    return json.loads(payload.decode("utf-8"))


@st.cache_data(ttl=240, show_spinner=False)
def _access_token() -> str:
    credentials = _credentials()
    if not credentials:
        raise RuntimeError("Falta configurar las credenciales API de Anura.")

    client_id, client_password = credentials
    data = _post_form(
        AUTH_URL,
        {"grant_type": "client_credentials"},
        client_id,
        client_password,
    )
    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Anura no devolvio access_token.")
    return access_token


def _request_json(path: str, params: dict[str, object] | None = None) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{API_BASE_URL}/{path.lstrip('/')}{query}",
        headers={"Authorization": f"Bearer {_access_token()}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Anura respondio error HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("No se pudo conectar con Anura.") from exc
    return json.loads(payload.decode("utf-8"))


def _date_time(value: str, end: bool = False) -> str:
    day = pd.to_datetime(value).strftime("%Y-%m-%d")
    return f"{day} {'23:59' if end else '00:00'}"


def _account_filter(zones: tuple[str, ...]) -> set[str]:
    if not zones:
        return {value.upper() for values in TELEMARKETING_ACCOUNTS.values() for value in values}

    selected: set[str] = set()
    for zone in zones:
        key = str(zone).strip().upper()
        selected.update(value.upper() for value in TELEMARKETING_ACCOUNTS.get(key, ()))
    return selected


def _parse_datetime_ms(value: object) -> pd.Timestamp:
    timestamp = pd.to_numeric(value, errors="coerce")
    if pd.isna(timestamp):
        return pd.NaT
    return pd.to_datetime(int(timestamp), unit="ms", utc=True).tz_convert("America/Buenos_Aires")


def _clean_name(value: object) -> str:
    text = str(value or "").upper()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^A-Z0-9 Ñ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_status(value: object) -> str:
    status = str(value or "").upper()
    return {
        "ANSWER": "Contestada",
        "NOANSWER": "No contestada",
        "BUSY": "Ocupado",
        "CANCEL": "Cancelada",
        "CANCELLED": "Cancelada",
        "CONGESTION": "Congestion",
        "FAILED": "Fallida",
    }.get(status, str(value or "Sin estado"))


@st.cache_data(ttl=300, show_spinner=False)
def calls(fecha_desde: str, fecha_hasta: str, zones: tuple[str, ...]) -> AnuraResult:
    if not _credentials():
        return AnuraResult(False, "Falta configurar las credenciales API de Anura.", pd.DataFrame())

    try:
        data = _request_json(
            "stats/cdrs/",
            {
                "startDate": _date_time(fecha_desde),
                "endDate": _date_time(fecha_hasta, end=True),
                "filter": "",
            },
        )
        rows: list[dict[str, object]] = []
        for item in data or []:
            account = item.get("account") or {}
            direction = str(item.get("direction") or "").upper()
            if direction != "OUT":
                continue

            origin_name = str(item.get("callingName") or account.get("name") or "").strip()
            origin_number = str(item.get("calling") or "").strip()
            rows.append(
                {
                    "fecha_hora": _parse_datetime_ms(item.get("dialTime")),
                    "direccion": "Saliente",
                    "telemarketer": origin_name,
                    "interno": origin_number,
                    "cliente": str(item.get("calledName") or "").strip(),
                    "telefono": str(item.get("called") or "").strip(),
                    "estado": _normalize_status(item.get("status")),
                    "duracion_seg": float(pd.to_numeric(item.get("billSeconds"), errors="coerce") or 0),
                    "duracion_total_seg": float(pd.to_numeric(item.get("duration"), errors="coerce") or 0),
                }
            )

        calls_df = pd.DataFrame(rows)
        if calls_df.empty:
            return AnuraResult(True, "Anura no devolvio llamadas salientes para el periodo.", calls_df)

        account_filter = _account_filter(zones)
        if account_filter:
            calls_df = calls_df[
                calls_df["interno"].astype(str).str.upper().isin(account_filter)
                | calls_df["telemarketer"].astype(str).str.upper().isin(account_filter)
            ].copy()

        calls_df["fecha_hora"] = pd.to_datetime(calls_df["fecha_hora"], errors="coerce")
        calls_df["fecha"] = calls_df["fecha_hora"].dt.date
        calls_df["cliente_normalizado"] = calls_df["cliente"].map(_clean_name)
        calls_df = calls_df.sort_values("fecha_hora", ascending=False)
        return AnuraResult(True, "OK", calls_df)
    except Exception as exc:
        return AnuraResult(False, str(exc), pd.DataFrame())


def summarize(calls_df: pd.DataFrame, sold_clients: pd.DataFrame) -> tuple[dict[str, float], pd.DataFrame]:
    if calls_df.empty:
        return (
            {
                "llamadas": 0,
                "contestadas": 0,
                "no_efectivas": 0,
                "clientes_llamados": 0,
                "minutos_hablados": 0.0,
                "llamados_con_venta": 0,
            },
            calls_df,
        )

    detail = calls_df.copy()
    sold_names = set(sold_clients.get("cliente", pd.Series(dtype=str)).map(_clean_name))

    def has_sale(name: object) -> bool:
        clean = _clean_name(name)
        if not clean:
            return False
        return any(clean in sold or sold in clean for sold in sold_names if sold)

    detail["venta_periodo"] = detail["cliente"].map(has_sale).map({True: "Con venta", False: "Sin venta"})
    answered = detail["estado"].str.upper().eq("CONTESTADA")
    with_sale = detail["venta_periodo"].eq("Con venta")
    return (
        {
            "llamadas": float(len(detail)),
            "contestadas": float(answered.sum()),
            "no_efectivas": float((~answered).sum()),
            "clientes_llamados": float(detail["cliente_normalizado"].replace("", pd.NA).dropna().nunique()),
            "minutos_hablados": float(detail["duracion_seg"].sum() / 60),
            "llamados_con_venta": float(with_sale.sum()),
        },
        detail,
    )
