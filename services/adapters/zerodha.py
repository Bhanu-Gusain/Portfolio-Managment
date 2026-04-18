"""Adapter for Zerodha Console exports (holdings, tradebook)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

NAME = "zerodha"
TARGET = "auto"


def matches(path: Path) -> bool:
    name = path.name.lower()
    if "zerodha" not in name and "console" not in name and "tradebook" not in name:
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

    # Tradebook: columns typically include trade_date, symbol, trade_type, quantity, price
    if "tradebook" in name or {"trade_date", "trade_type"}.issubset(cols):
        date_col = "trade_date" if "trade_date" in cols else "order_execution_time"
        out = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d"),
            "symbol": df["symbol"].str.strip(),
            "exchange": df.get("exchange", pd.Series(["NSE"] * len(df))).replace("", "NSE"),
            "side": df["trade_type"].str.lower().str.strip(),
            "quantity": pd.to_numeric(df["quantity"], errors="coerce"),
            "price": pd.to_numeric(df["price"], errors="coerce"),
            "charges": 0.0,
            "notes": "",
        })
        out.attrs["target"] = "stock_transactions"
        return out.dropna(subset=["quantity", "price", "date"]).reset_index(drop=True)

    # Holdings: columns include symbol, quantity, average_price
    if {"symbol", "quantity", "average price"}.issubset(cols) or {"symbol", "quantity", "average_price"}.issubset(cols):
        avg_col = "average price" if "average price" in cols else "average_price"
        out = pd.DataFrame({
            "symbol": df["symbol"].str.strip(),
            "exchange": df.get("exchange", pd.Series(["NSE"] * len(df))).replace("", "NSE"),
            "quantity": pd.to_numeric(df["quantity"], errors="coerce"),
            "avg_cost": pd.to_numeric(df[avg_col], errors="coerce"),
            "currency": "INR",
        })
        out.attrs["target"] = "stock_holdings"
        return out.dropna(subset=["quantity", "avg_cost"]).reset_index(drop=True)

    raise ValueError(
        f"Zerodha file {path.name} schema not recognised. Columns: {sorted(cols)}"
    )
