from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
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


API_BASE_URL = "https://api.persat.com.ar/v1"
ENCRYPTED_KEY_PATH = Path("data/persat_api_key.enc")
REQUEST_TIMEOUT_SECONDS = 20
EXCLUDED_CLIENT_NAMES = {
    "PERICH VIRGINIA FANNY",
    "BRAVO JORGE",
    "DOMICILIO CARINA",
}

ZONE_DEVICE_MAP: dict[str, tuple[int, ...]] = {
    "BRAVO": (3,),
    "CARINA": (4,),
    "FRANCISCO": (6,),
    "JONATAN MERCAO": (8,),
    "JUAN C. MANZELLI": (9,),
}


@dataclass(frozen=True)
class PersatResult:
    enabled: bool
    message: str
    devices: pd.DataFrame
    visits: pd.DataFrame


def _api_key() -> str | None:
    env_key = os.getenv("PERSAT_API_KEY")
    if env_key:
        return env_key.strip()
    try:
        key = st.secrets.get("persat", {}).get("api_key")
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
        raise RuntimeError("Falta configurar la API key de Persat.")

    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{API_BASE_URL}/{path.lstrip('/')}{query}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Persat respondio error HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("No se pudo conectar con Persat.") from exc

    data = json.loads(payload.decode("utf-8"))
    if not data.get("success", False):
        raise RuntimeError(str(data.get("message") or "Persat no devolvio una respuesta valida."))
    return data


@st.cache_data(ttl=300, show_spinner=False)
def devices() -> pd.DataFrame:
    data = _request_json("devices").get("data", [])
    rows: list[dict[str, object]] = []
    for item in data:
        working_zones = item.get("working_zones") or []
        rows.append(
            {
                "device_id": item.get("id"),
                "nombre": " ".join(
                    part.strip()
                    for part in (str(item.get("first_name") or ""), str(item.get("last_name") or ""))
                    if part.strip()
                ),
                "tipo": item.get("type"),
                "zonas_persat": ", ".join(str(zone.get("name") or "").strip() for zone in working_zones),
            }
        )
    return pd.DataFrame(rows)


def _month_keys(fecha_desde: str, fecha_hasta: str) -> list[str]:
    start = pd.to_datetime(fecha_desde).to_period("M")
    end = pd.to_datetime(fecha_hasta).to_period("M")
    return [str(value) for value in pd.period_range(start, end, freq="M")]


def _clean_client_name(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


@st.cache_data(ttl=300, show_spinner=False)
def _device_month_visits(device_id: int, month_key: str) -> pd.DataFrame:
    data = _request_json(f"devices-visits/{month_key}/{device_id}").get("data", [])
    rows: list[dict[str, object]] = []
    for item in data:
        client = item.get("client") or {}
        rows.append(
            {
                "device_id": int(item.get("device_id") or device_id),
                "fecha_hora": item.get("date"),
                "duracion_ms": item.get("duration") or 0,
                "id_cliente": str(client.get("uid_client") or "").strip(),
                "cliente": str(client.get("company_name") or "").strip(),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["device_id", "fecha_hora", "duracion_ms", "id_cliente", "cliente"])
    df = pd.DataFrame(rows)
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce", utc=True).dt.tz_convert(
        "America/Buenos_Aires"
    )
    df["fecha"] = df["fecha_hora"].dt.date
    df["duracion_min"] = pd.to_numeric(df["duracion_ms"], errors="coerce").fillna(0) / 60000
    df = df[~df["cliente"].map(_clean_client_name).isin(EXCLUDED_CLIENT_NAMES)].copy()
    return df


def device_ids_for_zones(zones: tuple[str, ...]) -> tuple[int, ...]:
    if not zones:
        return tuple(sorted({device_id for ids in ZONE_DEVICE_MAP.values() for device_id in ids}))
    ids: list[int] = []
    for zone in zones:
        clean_zone = str(zone).strip().upper()
        ids.extend(ZONE_DEVICE_MAP.get(clean_zone, ()))
    return tuple(dict.fromkeys(ids))


def activity(fecha_desde: str, fecha_hasta: str, zones: tuple[str, ...]) -> PersatResult:
    if not _api_key():
        return PersatResult(False, "Falta configurar la API key de Persat.", pd.DataFrame(), pd.DataFrame())

    try:
        devices_df = devices()
        device_ids = device_ids_for_zones(zones)
        if not device_ids:
            return PersatResult(
                True,
                "No hay dispositivo Persat asociado a esta zona.",
                devices_df,
                pd.DataFrame(columns=["device_id", "fecha_hora", "fecha", "id_cliente", "cliente", "duracion_min"]),
            )

        frames = [
            _device_month_visits(device_id, month_key)
            for device_id in device_ids
            for month_key in _month_keys(fecha_desde, fecha_hasta)
        ]
        visits = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if visits.empty:
            return PersatResult(True, "Persat no devolvio visitas para el periodo.", devices_df, visits)

        start_date = pd.to_datetime(fecha_desde).date()
        end_date = pd.to_datetime(fecha_hasta).date()
        visits = visits[(visits["fecha"] >= start_date) & (visits["fecha"] <= end_date)].copy()
        visits = visits.merge(
            devices_df.loc[:, ["device_id", "nombre"]],
            on="device_id",
            how="left",
        )
        visits["vendedor"] = visits["nombre"].fillna("Dispositivo " + visits["device_id"].astype(str))
        visits = visits.drop(columns=["nombre"])
        visits = visits.sort_values("fecha_hora", ascending=False)
        return PersatResult(True, "OK", devices_df, visits)
    except Exception as exc:
        return PersatResult(False, str(exc), pd.DataFrame(), pd.DataFrame())


def summarize(visits: pd.DataFrame, sold_clients: pd.DataFrame) -> dict[str, float]:
    if visits.empty:
        return {
            "visitas": 0,
            "clientes_visitados": 0,
            "duracion_promedio": 0.0,
            "visitados_con_venta": 0,
            "visitados_sin_venta": 0,
        }

    visited_ids = set(visits["id_cliente"].dropna().astype(str).str.strip())
    sold_ids = set(sold_clients.get("id_cliente", pd.Series(dtype=str)).dropna().astype(str).str.strip())
    with_sale = len(visited_ids & sold_ids)
    return {
        "visitas": float(len(visits)),
        "clientes_visitados": float(len(visited_ids)),
        "duracion_promedio": float(visits["duracion_min"].mean()) if "duracion_min" in visits else 0.0,
        "visitados_con_venta": float(with_sale),
        "visitados_sin_venta": float(max(len(visited_ids) - with_sale, 0)),
    }
