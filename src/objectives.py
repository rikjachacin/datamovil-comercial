from __future__ import annotations

from io import BytesIO
from calendar import monthrange
from pathlib import Path

import pandas as pd
import streamlit as st
from cryptography.fernet import Fernet, InvalidToken
from streamlit.errors import StreamlitSecretNotFoundError


OBJECTIVES_PATH = Path("data/objetivos.csv")
ENCRYPTED_OBJECTIVES_PATH = Path("data/objetivos.csv.enc")
SNAPSHOT_KEY_PATH = Path("data/snapshot.key")
REQUIRED_COLUMNS = ("mes", "zona", "objetivo")
HOLIDAYS = {
    "2026-05-25",
}


def month_key(value: object) -> str:
    return pd.to_datetime(value).strftime("%Y-%m")


def month_progress(fecha: object) -> float:
    current_date = pd.to_datetime(fecha).date()
    total_business_days = _business_days_in_month(current_date)
    elapsed_business_days = _business_days_between(current_date.replace(day=1), current_date)
    return min(elapsed_business_days / total_business_days, 1.0) if total_business_days else 1.0


def remaining_days(fecha: object) -> float:
    current_date = pd.to_datetime(fecha).date()
    days_in_month = monthrange(current_date.year, current_date.month)[1]
    month_end = current_date.replace(day=days_in_month)
    return max(_business_days_between(current_date, month_end), 1)


def business_days_in_month(fecha: object) -> float:
    return _business_days_in_month(fecha)


def business_days_between(start: object, end: object) -> float:
    return _business_days_between(start, end)


def _business_days_in_month(fecha: object) -> float:
    current_date = pd.to_datetime(fecha).date()
    days_in_month = monthrange(current_date.year, current_date.month)[1]
    return _business_days_between(current_date.replace(day=1), current_date.replace(day=days_in_month))


def _business_days_between(start: object, end: object) -> float:
    start_date = pd.to_datetime(start).date()
    end_date = pd.to_datetime(end).date()
    if start_date > end_date:
        return 0.0
    days = pd.date_range(start=start_date, end=end_date, freq="D")
    total = 0.0
    for day in days:
        date_value = day.date()
        if date_value.isoformat() in HOLIDAYS:
            continue
        if date_value.weekday() < 5:
            total += 1.0
        elif date_value.weekday() == 5:
            total += 0.5
    return total


def load_objectives(path: Path = OBJECTIVES_PATH) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path)
    elif ENCRYPTED_OBJECTIVES_PATH.exists():
        key = _snapshot_key()
        if not key:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)
        try:
            data = Fernet(key.encode("utf-8")).decrypt(ENCRYPTED_OBJECTIVES_PATH.read_bytes())
        except (InvalidToken, ValueError) as exc:
            raise RuntimeError("La clave data.snapshot_key no puede abrir los objetivos cifrados.") from exc
        df = pd.read_csv(BytesIO(data))
    else:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise RuntimeError(f"Faltan columnas en {path}: {', '.join(missing)}")

    out = df.loc[:, REQUIRED_COLUMNS].copy()
    out["mes"] = out["mes"].astype(str).str[:7]
    out["zona"] = out["zona"].astype(str).str.strip()
    out["objetivo"] = pd.to_numeric(out["objetivo"], errors="coerce").fillna(0)
    return out


def _snapshot_key() -> str | None:
    try:
        key = st.secrets.get("data", {}).get("snapshot_key")
        if key:
            return str(key).strip()
    except StreamlitSecretNotFoundError:
        pass
    if SNAPSHOT_KEY_PATH.exists():
        return SNAPSHOT_KEY_PATH.read_text(encoding="utf-8").strip()
    return None


def monthly_performance(
    ventas_zona: pd.DataFrame,
    objetivos: pd.DataFrame,
    mes: str,
    avance_mes: float,
    dias_restantes: float,
) -> pd.DataFrame:
    base = ventas_zona.loc[:, ["zona", "total", "comprobantes", "clientes"]].copy()
    base = base.rename(columns={"total": "ventas_mes"})

    current_objectives = objetivos[objetivos["mes"] == mes].copy()
    out = base.merge(current_objectives[["zona", "objetivo"]], on="zona", how="left")
    out["objetivo"] = out["objetivo"].fillna(0)
    out["tiene_objetivo"] = out["objetivo"] > 0
    out["cumplimiento"] = out.apply(
        lambda row: row["ventas_mes"] / row["objetivo"] if row["objetivo"] else 0,
        axis=1,
    )
    out["objetivo_esperado"] = out["objetivo"] * avance_mes
    out["ritmo"] = out.apply(
        lambda row: row["ventas_mes"] / row["objetivo_esperado"] if row["objetivo_esperado"] else 0,
        axis=1,
    )
    out["brecha_esperada"] = out["ventas_mes"] - out["objetivo_esperado"]
    out["proyeccion_cierre"] = out.apply(
        lambda row: row["ventas_mes"] / avance_mes if avance_mes else row["ventas_mes"],
        axis=1,
    )
    out["brecha_objetivo"] = out["ventas_mes"] - out["objetivo"]
    out["venta_diaria_necesaria"] = out.apply(
        lambda row: max(row["objetivo"] - row["ventas_mes"], 0) / dias_restantes
        if dias_restantes and row["objetivo"]
        else 0,
        axis=1,
    )
    out["estado"] = out["ritmo"].map(_status)
    return out.sort_values(["ritmo", "ventas_mes"], ascending=[False, False])


def _status(value: float) -> str:
    if value >= 1:
        return "En ritmo"
    if value >= 0.85:
        return "Cerca"
    return "Necesita impulso"


def executive_insights(performance: pd.DataFrame) -> dict[str, object]:
    scoped = performance[performance["tiene_objetivo"]].copy()
    if scoped.empty:
        return {
            "leader": None,
            "risk": None,
            "recovery_daily": 0.0,
            "below_pace": 0,
            "message": "No hay objetivos cargados para el mes.",
        }

    leader = scoped.sort_values(["ritmo", "ventas_mes"], ascending=[False, False]).iloc[0]
    risk = scoped.sort_values(["brecha_esperada", "ritmo"], ascending=[True, True]).iloc[0]
    below_pace = int((scoped["ritmo"] < 1).sum())
    recovery_daily = scoped["venta_diaria_necesaria"].sum()

    if below_pace == 0:
        message = "El equipo esta por encima del ritmo esperado. Mantener frecuencia de visita y cuidar reposicion."
    elif below_pace <= max(len(scoped) // 3, 1):
        message = "Hay pocas zonas bajo ritmo. Conviene concentrar apoyo puntual sin cambiar la estrategia general."
    else:
        message = "La mayoria del equipo esta bajo ritmo. Priorizar visitas de recuperacion y foco diario por zona."

    return {
        "leader": leader,
        "risk": risk,
        "recovery_daily": recovery_daily,
        "below_pace": below_pace,
        "message": message,
    }
