"""Adapter for Groww exports (equity holdings, MF holdings)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

NAME = "groww"
# TARGET is decided per-file by matches(); see route() in __init__.
TARGET = "auto"


_EQUITY_COLS = {"stock name", "isin", "quantity", "average buy price"}
_MF_COLS = {"scheme name", "units", "nav"}


def matches(path: Path) -> bool:
    name = path.name.lower()
    if not name.startswith("groww"):
        return False
    return path.suffix.lower() in {".csv", ".xlsx", ".xls"}


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    elif path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path, engine="openpyxl", dtype=str)
    else:
        df = pd.read_excel(path, engine="xlrd", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    return df.fillna("")


def parse(path: Path) -> pd.DataFrame:
    df = _read(path)
    cols = set(df.columns)

    if _EQUITY_COLS.issubset(cols):
        out = pd.DataFrame({
            "symbol": df["stock name"].str.strip(),
            "exchange": df.get("exchange", pd.Series(["NSE"] * len(df))).replace("", "NSE"),
            "quantity": pd.to_numeric(df["quantity"], errors="coerce"),
            "avg_cost": pd.to_numeric(df["average buy price"], errors="coerce"),
            "currency": "INR",
        })
        # Stamp the target for the router
        out.attrs["target"] = "stock_holdings"
        return out.dropna(subset=["quantity", "avg_cost"]).reset_index(drop=True)

    if _MF_COLS.issubset(cols):
        out = pd.DataFrame({
            "isin": df.get("isin", pd.Series([""] * len(df))).str.strip().str.upper(),
            "scheme_name": df["scheme name"].str.strip(),
            "units": pd.to_numeric(df["units"], errors="coerce"),
            "avg_nav": pd.to_numeric(df.get("avg nav", df["nav"]), errors="coerce"),
        })
        out.attrs["target"] = "mf_holdings"
        return out.dropna(subset=["units", "avg_nav"]).reset_index(drop=True)

    raise ValueError(
        f"Groww file {path.name} does not match equity or MF schema. "
        f"Columns found: {sorted(cols)}"
    )


# Router consults `.attrs["target"]` after parse() for groww because it serves both
# equity and MF files.
def _target_for(df: pd.DataFrame) -> str:
    return df.attrs.get("target", "stock_holdings")
