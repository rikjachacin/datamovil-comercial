from __future__ import annotations

from datetime import date
import math

import pandas as pd


CAMPAIGN_START_DATE = date(2026, 6, 25)
CAMPAIGN_END_DATE = date(2026, 10, 31)
TARGET_COVERAGE = 0.30
BOX_CODES = ("AUKI04", "AUKI08")

# Bases congeladas para que la meta de octubre no cambie por reasignaciones.
# Lucia se evalua sobre sus 93 clientes activos de los ultimos cuatro meses.
PORTFOLIO_BASES = {
    "BRAVO": 95,
    "CARINA": 86,
    "CECILIA": 9,
    "DAVID": 343,
    "JUAN C. MANZELLI": 102,
    "LUCIA MORENO": 93,
    "MACA PROTTO": 232,
    "MICAELA GONZALEZ": 141,
    "NOELIA": 205,
    "ZONA 13 JAVIER MOLARO": 101,
}


def campaign_cutoff(cutoff: object) -> date:
    return min(pd.to_datetime(cutoff).date(), CAMPAIGN_END_DATE)


def coverage_summary(buyers: pd.DataFrame, zones: tuple[str, ...]) -> pd.DataFrame:
    selected = list(dict.fromkeys(str(zone).strip().upper() for zone in zones))
    selected = [zone for zone in selected if zone in PORTFOLIO_BASES]
    summary = pd.DataFrame(
        {
            "zona": selected,
            "base_evaluable": [PORTFOLIO_BASES[zone] for zone in selected],
        }
    )
    if summary.empty:
        return pd.DataFrame(
            columns=[
                "zona",
                "base_evaluable",
                "clientes_con_caja",
                "meta_clientes",
                "faltan",
                "cobertura_pct",
                "cumplimiento_pct",
            ]
        )

    valid = buyers.copy()
    if valid.empty:
        counts = pd.DataFrame(columns=["zona", "clientes_con_caja"])
    else:
        valid["zona"] = valid["zona"].fillna("").astype(str).str.strip().str.upper()
        valid["cajas_netas"] = pd.to_numeric(valid["cajas_netas"], errors="coerce").fillna(0)
        valid = valid[valid["cajas_netas"] >= 1]
        counts = (
            valid.groupby("zona", as_index=False)["id_cliente"]
            .nunique()
            .rename(columns={"id_cliente": "clientes_con_caja"})
        )

    summary = summary.merge(counts, on="zona", how="left")
    summary["clientes_con_caja"] = summary["clientes_con_caja"].fillna(0).astype(int)
    summary["meta_clientes"] = summary["base_evaluable"].map(
        lambda value: math.ceil(value * TARGET_COVERAGE)
    )
    summary["faltan"] = (summary["meta_clientes"] - summary["clientes_con_caja"]).clip(lower=0)
    summary["cobertura_pct"] = (
        100 * summary["clientes_con_caja"] / summary["base_evaluable"]
    ).round(1)
    summary["cumplimiento_pct"] = (
        100 * summary["clientes_con_caja"] / summary["meta_clientes"]
    ).round(1)
    return summary.sort_values("zona").reset_index(drop=True)
