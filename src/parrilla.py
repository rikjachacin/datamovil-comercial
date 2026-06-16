from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import unicodedata

import pandas as pd

from src import siscor_db

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = ValueError


OBJECTIVES_PATH = Path("data/parrilla_objetivos.csv")
OBJECTIVES_COLUMNS = ["mes", "laboratorio", "vendedor", "objetivo"]
EXCLUDED_LABORATORIES: set[str] = set()
LABORATORY_ALIASES = {
    "VACACIONES": "Holliday",
    "HOLLIDAY": "Holliday",
}

VENDOR_ALIASES = {
    "BRAVO": "Bravo",
    "CARINA": "Carina",
    "DAVID": "David",
    "FRANCISCO": "Francisco",
    "JONATAN": "Jonatan",
    "JONATANMERCAO": "Jonatan",
    "JUANCRUZ": "Juan Cruz",
    "JUANCRUZM": "Juan Cruz",
    "JUANCMANZELLI": "Juan Cruz",
    "LUCIA": "Lucia",
    "MACARENA": "Macarena",
    "MACA": "Macarena",
    "MACAPROTTO": "Macarena",
    "MICAELA": "Micaela",
    "MICAELAGONZALEZ": "Micaela",
    "NOELIA": "Noelia",
    "JAVIER": "Javier",
    "JAVIERMOLARO": "Javier",
    "ZONA13JAVIERMOLARO": "Javier",
}


@dataclass(frozen=True)
class ParrillaResult:
    enabled: bool
    message: str
    data: pd.DataFrame


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.upper() if char.isalnum())


def canonical_vendor(value: object) -> str:
    normalized = normalize(value)
    if normalized in VENDOR_ALIASES:
        return VENDOR_ALIASES[normalized]
    for alias, vendor in VENDOR_ALIASES.items():
        if alias and alias in normalized:
            return vendor
    return str(value or "").strip()


def canonical_laboratory(value: object) -> str:
    normalized = normalize(value)
    if normalized in LABORATORY_ALIASES:
        return LABORATORY_ALIASES[normalized]
    return str(value or "").strip()


def is_excluded_laboratory(value: object) -> bool:
    return normalize(value) in EXCLUDED_LABORATORIES


def load_objectives() -> pd.DataFrame:
    csv_path = OBJECTIVES_PATH
    encrypted_path = Path(f"{OBJECTIVES_PATH}.enc")
    if encrypted_path.exists():
        if Fernet is None:
            raise RuntimeError("Falta cryptography para leer objetivos de parrilla cifrados.")
        key = siscor_db._snapshot_key()
        if not key:
            raise RuntimeError("Falta la clave snapshot para leer objetivos de parrilla cifrados.")
        try:
            content = Fernet(key.encode("utf-8")).decrypt(encrypted_path.read_bytes())
        except (InvalidToken, ValueError) as exc:
            raise RuntimeError("No pude descifrar objetivos de parrilla.") from exc
        df = pd.read_csv(BytesIO(content))
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        return pd.DataFrame(columns=OBJECTIVES_COLUMNS)

    for column in OBJECTIVES_COLUMNS:
        if column not in df.columns:
            df[column] = "" if column != "objetivo" else 0
    df = df.loc[:, OBJECTIVES_COLUMNS].copy()
    df = df[~df["laboratorio"].map(is_excluded_laboratory)].copy()
    df["laboratorio"] = df["laboratorio"].map(canonical_laboratory)
    df["vendedor"] = df["vendedor"].map(canonical_vendor)
    df["objetivo"] = siscor_db._to_numeric_amount(df["objetivo"])
    return df[df["laboratorio"].ne("") & df["vendedor"].ne("")]


def available_vendors(objectives: pd.DataFrame | None = None) -> list[str]:
    df = load_objectives() if objectives is None else objectives
    if df.empty or "vendedor" not in df.columns:
        return []
    return sorted(df["vendedor"].dropna().astype(str).unique())


def build_progress(
    objectives: pd.DataFrame,
    sales_by_brand: pd.DataFrame,
    vendor: str | None = None,
) -> ParrillaResult:
    columns = ["vendedor", "laboratorio", "objetivo", "facturado", "cumplimiento"]
    if objectives.empty:
        return ParrillaResult(False, "No hay objetivos de parrilla cargados.", pd.DataFrame(columns=columns))
    if sales_by_brand.empty:
        return ParrillaResult(
            False,
            "No hay ventas por marca disponibles. Actualiza el snapshot con la columna marca.",
            pd.DataFrame(columns=columns),
        )

    scoped_objectives = objectives.copy()
    scoped_objectives = scoped_objectives[~scoped_objectives["laboratorio"].map(is_excluded_laboratory)].copy()
    scoped_objectives["laboratorio"] = scoped_objectives["laboratorio"].map(canonical_laboratory)
    if vendor:
        vendor_name = canonical_vendor(vendor)
        scoped_objectives = scoped_objectives[scoped_objectives["vendedor"].map(canonical_vendor).eq(vendor_name)]
    if scoped_objectives.empty:
        return ParrillaResult(False, "No hay objetivos de parrilla para este vendedor.", pd.DataFrame(columns=columns))

    sales = sales_by_brand.copy()
    sales = sales[~sales["marca"].map(is_excluded_laboratory)].copy()
    sales["vendedor"] = sales["zona"].map(canonical_vendor)
    sales["marca_norm"] = sales["marca"].map(normalize)
    sales["total"] = siscor_db._to_numeric_amount(sales["total"])

    labs = scoped_objectives.loc[:, ["laboratorio"]].drop_duplicates().copy()
    labs["lab_norm"] = labs["laboratorio"].map(normalize)
    labs = labs.sort_values("lab_norm", key=lambda series: series.str.len(), ascending=False)

    matched_rows: list[dict[str, object]] = []
    for _, sale in sales.iterrows():
        sale_norm = str(sale["marca_norm"])
        if not sale_norm:
            continue
        for _, lab in labs.iterrows():
            lab_norm = str(lab["lab_norm"])
            if _brand_matches_laboratory(sale_norm, lab_norm):
                matched_rows.append(
                    {
                        "vendedor": sale["vendedor"],
                        "laboratorio": lab["laboratorio"],
                        "facturado": sale["total"],
                    }
                )
                break

    if matched_rows:
        matched = pd.DataFrame(matched_rows)
        matched = matched.groupby(["vendedor", "laboratorio"], as_index=False).agg(facturado=("facturado", "sum"))
    else:
        matched = pd.DataFrame(columns=["vendedor", "laboratorio", "facturado"])

    out = scoped_objectives.merge(matched, on=["vendedor", "laboratorio"], how="left")
    out["facturado"] = out["facturado"].fillna(0.0)
    out["cumplimiento"] = out.apply(
        lambda row: (float(row["facturado"]) / float(row["objetivo"]) * 100) if float(row["objetivo"]) else 0.0,
        axis=1,
    )
    out = out.loc[:, columns].sort_values(["vendedor", "cumplimiento", "laboratorio"], ascending=[True, False, True])
    return ParrillaResult(True, "OK", out)


def _brand_matches_laboratory(brand_norm: str, laboratory_norm: str) -> bool:
    if not brand_norm or not laboratory_norm:
        return False
    if laboratory_norm == "HOLLIDAY":
        return brand_norm == "HOLLIDAY"
    if laboratory_norm == "MVHOLLIDAY":
        return brand_norm == "MVHOLLIDAY"
    return laboratory_norm in brand_norm or brand_norm in laboratory_norm
