"""Tests for services.adapters — router + individual adapters."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.adapters import UnsupportedFileError, route


def test_router_rejects_unknown(tmp_path: Path) -> None:
    p = tmp_path / "myfile.csv"
    p.write_text("a,b\n1,2\n")
    try:
        route(p)
    except UnsupportedFileError:
        return
    raise AssertionError("Expected UnsupportedFileError")


def test_groww_equity_routed(tmp_path: Path) -> None:
    p = tmp_path / "groww_equity_apr.csv"
    pd.DataFrame([{
        "Stock Name": "RELIANCE.NS", "ISIN": "INE002A01018",
        "Quantity": 5, "Average buy price": 2400.0,
    }]).to_csv(p, index=False)
    pairs = route(p)
    assert len(pairs) == 1
    target, df = pairs[0]
    assert target == "stock_holdings"
    assert df.iloc[0]["symbol"] == "RELIANCE.NS"
    assert df.iloc[0]["quantity"] == 5


def test_kuvera_mf_holdings_routed(tmp_path: Path) -> None:
    p = tmp_path / "kuvera_mf_holdings.csv"
    pd.DataFrame([{
        "ISIN": "INF879O01019", "scheme_name": "PPFC", "units": 100, "avg_nav": 55.0,
    }]).to_csv(p, index=False)
    pairs = route(p)
    assert len(pairs) == 1
    target, df = pairs[0]
    assert target == "mf_holdings"
    assert df.iloc[0]["isin"] == "INF879O01019"


def test_zerodha_tradebook_routed(tmp_path: Path) -> None:
    p = tmp_path / "zerodha_tradebook.csv"
    pd.DataFrame([{
        "trade_date": "2024-01-15", "symbol": "TCS",
        "trade_type": "buy", "quantity": 5, "price": 3300.0, "exchange": "NSE",
    }]).to_csv(p, index=False)
    pairs = route(p)
    assert len(pairs) == 1
    target, df = pairs[0]
    assert target == "stock_transactions"
    assert df.iloc[0]["side"] == "buy"
