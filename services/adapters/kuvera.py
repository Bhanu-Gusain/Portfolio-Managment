"""Adapter for Kuvera exports (MF holdings, MF transactions)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

NAME = "kuvera"
TARGET = "auto"


def matches(path: Path) -> bool:
    name = path.name.lower()
    if not name.startswith("kuvera"):
        return False
    return path.suffix.lower() in {".csv", ".xlsx"}


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(path, engine="openpyxl", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    return df.fillna("")


def parse(path: Path) -> pd.DataFrame:
    df = _read(path)
    cols = set(df.columns)
    name = path.name.lower()

    if "transaction" in name or {"transaction_date", "transaction_type"}.issubset(cols):
        date_col = "transaction_date" if "transaction_date" in cols else "date"
        out = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d"),
            "isin": df.get("isin", pd.Series([""] * len(df))).str.strip().str.upper(),
            "scheme_name": df.get("scheme_name", df.get("scheme name", pd.Series([""] * len(df)))).str.strip(),
            "side": df.get("transaction_type", df.get("type", pd.Series(["buy"] * len(df)))).str.lower().str.strip(),
            "units": pd.to_numeric(df.get("units"), errors="coerce"),
            "nav": pd.to_numeric(df.get("nav", df.get("price")), errors="coerce"),
            "amount": pd.to_numeric(df.get("amount"), errors="coerce"),
            "folio": df.get("folio", pd.Series([""] * len(df))).astype(str),
            "notes": "",
        })
        out.attrs["target"] = "mf_transactions"
        return out.dropna(subset=["date", "units"]).reset_index(drop=True)

    if "holding" in name or {"scheme_name", "units"}.issubset(cols) or {"scheme name", "units"}.issubset(cols):
        scheme_col = "scheme_name" if "scheme_name" in cols else "scheme name"
        nav_col = "avg_nav" if "avg_nav" in cols else ("avg nav" if "avg nav" in cols else "nav")
        out = pd.DataFrame({
            "isin": df.get("isin", pd.Series([""] * len(df))).str.strip().str.upper(),
            "scheme_name": df[scheme_col].str.strip(),
            "units": pd.to_numeric(df["units"], errors="coerce"),
            "avg_nav": pd.to_numeric(df[nav_col], errors="coerce"),
        })
        out.attrs["target"] = "mf_holdings"
        return out.dropna(subset=["units", "avg_nav"]).reset_index(drop=True)

    raise ValueError(
        f"Kuvera file {path.name} schema not recognised. Columns: {sorted(cols)}"
    )
