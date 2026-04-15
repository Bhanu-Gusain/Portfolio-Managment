from __future__ import annotations

import pandas as pd
import pytest

from core.portfolio_engine import compute_positions, portfolio_summary
from db.repositories import holdings_repo, prices_repo


def _seed_price(symbol: str, close: float):
    df = pd.DataFrame([
        {"date": "2026-04-14", "open": close, "high": close, "low": close, "close": close, "volume": 1000},
    ])
    prices_repo.upsert_prices(symbol, df)


def test_empty_portfolio_returns_zero_summary():
    s = portfolio_summary()
    assert s["num_positions"] == 0
    assert s["total_value"] == 0


def test_compute_positions_basic():
    holdings_repo.upsert_stock("A.NS", "Alpha")
    holdings_repo.upsert_stock("B.NS", "Beta")
    holdings_repo.replace_holdings([("A.NS", 10, 100.0), ("B.NS", 5, 200.0)])
    _seed_price("A.NS", 120.0)
    _seed_price("B.NS", 220.0)

    positions = compute_positions()
    assert len(positions) == 2
    by = {p.symbol: p for p in positions}
    assert by["A.NS"].current_value == 1200.0
    assert by["A.NS"].pnl == 200.0
    assert by["B.NS"].current_value == 1100.0
    total = 1200 + 1100
    assert abs(by["A.NS"].allocation_pct - 1200 / total * 100) < 1e-6


def test_missing_price_fails_loud():
    holdings_repo.upsert_stock("X.NS", "X")
    holdings_repo.replace_holdings([("X.NS", 1, 50.0)])
    with pytest.raises(RuntimeError):
        compute_positions()
