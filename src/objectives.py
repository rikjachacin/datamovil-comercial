from __future__ import annotations

from calendar import monthrange
from pathlib import Path

import pandas as pd


OBJECTIVES_PATH = Path("data/objetivos.csv")
REQUIRED_COLUMNS = ("mes", "zona", "objetivo")


def month_key(value: object) -> str:
    return pd.to_datetime(value).strftime("%Y-%m")


def month_progress(fecha: object) -> float:
    current_date = pd.to_datetime(fecha).date()
    days_in_month = monthrange(current_date.year, current_date.month)[1]
    return min(current_date.day / days_in_month, 1.0)


def load_objectives(path: Path = OBJECTIVES_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise RuntimeError(f"Faltan columnas en {path}: {', '.join(missing)}")

    out = df.loc[:, REQUIRED_COLUMNS].copy()
    out["mes"] = out["mes"].astype(str).str[:7]
    out["zona"] = out["zona"].astype(str).str.strip()
    out["objetivo"] = pd.to_numeric(out["objetivo"], errors="coerce").fillna(0)
    return out


def monthly_performance(
    ventas_zona: pd.DataFrame,
    objetivos: pd.DataFrame,
    mes: str,
    avance_mes: float,
) -> pd.DataFrame:
    base = ventas_zona.loc[:, ["zona", "total", "comprobantes", "clientes"]].copy()
    base = base.rename(columns={"total": "ventas_mes"})

    current_objectives = objetivos[objetivos["mes"] == mes].copy()
    out = base.merge(current_objectives[["zona", "objetivo"]], on="zona", how="left")
    out["objetivo"] = out["objetivo"].fillna(0)
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
    out["estado"] = out["ritmo"].map(_status)
    return out.sort_values(["ritmo", "ventas_mes"], ascending=[False, False])


def _status(value: float) -> str:
    if value >= 1:
        return "En ritmo"
    if value >= 0.85:
        return "Cerca"
    return "Necesita impulso"
