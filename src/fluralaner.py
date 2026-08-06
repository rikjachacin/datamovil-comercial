from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet, InvalidToken

from src import siscor_db


OBJECTIVES_PATH = Path("data/fluralaner_objetivos.csv")
ENCRYPTED_OBJECTIVES_PATH = Path("data/fluralaner_objetivos.csv.enc")
PRODUCT_ORDER = ("Feline Full", "Bit Trio", "Ectholaner", "Zanex")
INCENTIVE_PER_UNIT = {
    "Feline Full": 600.0,
    "Bit Trio": 750.0,
    "Ectholaner": 500.0,
    "Zanex": 0.0,
}
REQUIRED_COLUMNS = ("zona", "producto", "objetivo")


def load_objectives() -> pd.DataFrame:
    if OBJECTIVES_PATH.exists():
        df = pd.read_csv(OBJECTIVES_PATH)
    elif ENCRYPTED_OBJECTIVES_PATH.exists():
        key = siscor_db._snapshot_key()
        if not key:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)
        try:
            content = Fernet(key.encode("utf-8")).decrypt(ENCRYPTED_OBJECTIVES_PATH.read_bytes())
        except (InvalidToken, ValueError) as exc:
            raise RuntimeError("La clave snapshot no puede abrir los objetivos de Fluralaner.") from exc
        df = pd.read_csv(BytesIO(content))
    else:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise RuntimeError(f"Faltan columnas en los objetivos de Fluralaner: {', '.join(missing)}")

    out = df.loc[:, REQUIRED_COLUMNS].copy()
    out["zona"] = out["zona"].fillna("").astype(str).str.strip().str.upper()
    out["producto"] = out["producto"].fillna("").astype(str).str.strip()
    out["objetivo"] = pd.to_numeric(out["objetivo"], errors="coerce").fillna(0)
    return out[out["producto"].isin(PRODUCT_ORDER)].copy()


def seller_summary(sales: pd.DataFrame, zones: tuple[str, ...]) -> pd.DataFrame:
    base = pd.DataFrame({"producto": PRODUCT_ORDER})
    if sales.empty:
        units = pd.DataFrame(columns=["producto", "unidades_vendidas"])
    else:
        units = (
            sales.groupby("producto", as_index=False)["unidades"]
            .sum()
            .rename(columns={"unidades": "unidades_vendidas"})
        )
    base = base.merge(units, on="producto", how="left")
    base["unidades_vendidas"] = pd.to_numeric(base["unidades_vendidas"], errors="coerce").fillna(0)

    normalized_zones = {str(zone).strip().upper() for zone in zones}
    objectives = load_objectives()
    objectives = objectives[objectives["zona"].isin(normalized_zones)]
    objectives = objectives.groupby("producto", as_index=False)["objetivo"].sum()
    base = base.merge(objectives, on="producto", how="left")
    base["objetivo"] = pd.to_numeric(base["objetivo"], errors="coerce").fillna(0)
    base["incentivo_acumulado"] = base.apply(
        lambda row: row["unidades_vendidas"] * INCENTIVE_PER_UNIT[row["producto"]],
        axis=1,
    )
    return base.loc[:, ["producto", "unidades_vendidas", "objetivo", "incentivo_acumulado"]]
