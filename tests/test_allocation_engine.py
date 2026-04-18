"""Tests for core.allocation_engine."""
from __future__ import annotations

import pandas as pd

from core.allocation_engine import by_asset_type, by_market_cap, by_mf_category, by_sector


def _positions() -> pd.DataFrame:
    return pd.DataFrame([
        {"asset_type": "stock", "identifier": "A.NS", "name": "A", "quantity": 1,
         "avg_cost": 100, "ltp": 120, "invested": 100, "current_value": 120,
         "pnl": 20, "pnl_pct": 20, "weight_pct": 60, "day_change_pct": None},
        {"asset_type": "stock", "identifier": "B.NS", "name": "B", "quantity": 1,
         "avg_cost": 50, "ltp": 40, "invested": 50, "current_value": 40,
         "pnl": -10, "pnl_pct": -20, "weight_pct": 20, "day_change_pct": None},
        {"asset_type": "mutual_fund", "identifier": "INF000A00001", "name": "MF",
         "quantity": 10, "avg_cost": 3, "ltp": 4, "invested": 30, "current_value": 40,
         "pnl": 10, "pnl_pct": 33.3, "weight_pct": 20, "day_change_pct": None},
    ])


def test_by_asset_type() -> None:
    agg = by_asset_type(_positions())
    assert set(agg["asset_type"]) == {"stock", "mutual_fund"}
    assert abs(agg["weight_pct"].sum() - 100.0) < 0.01


def test_by_sector() -> None:
    agg = by_sector(_positions(), {"A.NS": "IT", "B.NS": "Financials"})
    assert set(agg["sector"]) == {"IT", "Financials"}
    it_row = agg[agg["sector"] == "IT"].iloc[0]
    fin_row = agg[agg["sector"] == "Financials"].iloc[0]
    assert it_row["value"] == 120
    assert fin_row["value"] == 40


def test_by_market_cap() -> None:
    agg = by_market_cap(_positions(), {"A.NS": "Large", "B.NS": "Mid"})
    assert set(agg["market_cap"]) == {"Large", "Mid"}


def test_by_mf_category() -> None:
    mf_prices = pd.DataFrame([{
        "isin": "INF000A00001", "nav": 4, "scheme_name": "MF",
        "category": "Equity: Large Cap", "nav_date": "2026-04-18", "scheme_code": "99",
    }])
    agg = by_mf_category(_positions(), mf_prices)
    assert agg.iloc[0]["category"] == "Equity: Large Cap"
