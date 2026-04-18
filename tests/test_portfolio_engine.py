"""Tests for core.portfolio_engine.build_positions + summarise."""
from __future__ import annotations

import pandas as pd

from core.portfolio_engine import build_positions, summarise


def test_build_positions_with_prices() -> None:
    stocks = pd.DataFrame([{"symbol": "A.NS", "exchange": "NSE", "quantity": 10, "avg_cost": 100.0, "currency": "INR"}])
    mfs = pd.DataFrame([{"isin": "INF000A00001", "scheme_name": "X", "units": 100, "avg_nav": 50.0}])
    stock_prices = pd.DataFrame([{
        "symbol": "A.NS", "ltp": 120.0, "prev_close": 115.0, "day_change_pct": 4.3,
        "high_52w": 130.0, "low_52w": 90.0, "currency": "INR",
    }])
    mf_prices = pd.DataFrame([{
        "isin": "INF000A00001", "nav": 60.0, "scheme_name": "X",
        "category": "Equity: Flexi Cap", "nav_date": "2026-04-18", "scheme_code": "123",
    }])
    pos = build_positions(stocks, mfs, stock_prices, mf_prices)
    assert len(pos) == 2
    stock_row = pos[pos["identifier"] == "A.NS"].iloc[0]
    assert stock_row["current_value"] == 1200.0
    assert stock_row["pnl"] == 200.0
    mf_row = pos[pos["identifier"] == "INF000A00001"].iloc[0]
    assert mf_row["current_value"] == 6000.0
    # Weights sum to 100
    assert abs(pos["weight_pct"].sum() - 100.0) < 0.01


def test_build_positions_missing_price() -> None:
    stocks = pd.DataFrame([{"symbol": "X.NS", "exchange": "NSE", "quantity": 5, "avg_cost": 100.0, "currency": "INR"}])
    pos = build_positions(stocks, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert len(pos) == 1
    assert pos.iloc[0]["ltp"] is None or pd.isna(pos.iloc[0]["ltp"])
    assert pos.iloc[0]["current_value"] is None or pd.isna(pos.iloc[0]["current_value"])


def test_summarise_empty() -> None:
    s = summarise(pd.DataFrame())
    assert s["total_value"] == 0.0
    assert s["num_positions"] == 0


def test_summarise_aggregates() -> None:
    pos = pd.DataFrame([
        {"asset_type": "stock", "identifier": "A", "name": "A", "quantity": 1, "avg_cost": 100.0,
         "ltp": 120.0, "invested": 100.0, "current_value": 120.0, "pnl": 20.0, "pnl_pct": 20.0,
         "weight_pct": 100.0, "day_change_pct": None},
    ])
    s = summarise(pos, realised_ytd=50.0)
    assert s["total_value"] == 120.0
    assert s["total_invested"] == 100.0
    assert s["realised_ytd"] == 50.0
