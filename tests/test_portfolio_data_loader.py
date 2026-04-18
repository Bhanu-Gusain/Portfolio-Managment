"""Tests for services.portfolio_data_loader."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.portfolio_data_loader import load, SCHEMAS


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)


def test_load_empty_folder(isolated_portfolio_data: Path) -> None:
    data = load()
    assert data.is_empty()
    for name in SCHEMAS:
        df = getattr(data, name)
        assert list(df.columns) == SCHEMAS[name]


def test_load_canonical_stock_holdings(isolated_portfolio_data: Path) -> None:
    _write_csv(
        isolated_portfolio_data / "stock_holdings.csv",
        [{"symbol": "RELIANCE.NS", "exchange": "NSE", "quantity": "5",
          "avg_cost": "2400", "currency": "INR"}],
        SCHEMAS["stock_holdings"],
    )
    data = load()
    assert len(data.stock_holdings) == 1
    assert data.stock_holdings.iloc[0]["symbol"] == "RELIANCE.NS"
    assert data.stock_holdings.iloc[0]["quantity"] == 5.0
    assert "stock_holdings.csv" in data.loaded_files


def test_missing_required_columns_raises(isolated_portfolio_data: Path) -> None:
    pd.DataFrame([{"symbol": "X.NS", "quantity": "1"}]).to_csv(
        isolated_portfolio_data / "stock_holdings.csv", index=False
    )
    try:
        load()
    except ValueError as exc:
        assert "missing required columns" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing columns")


def test_isin_uppercased(isolated_portfolio_data: Path) -> None:
    _write_csv(
        isolated_portfolio_data / "mf_holdings.csv",
        [{"isin": "inf879o01019", "scheme_name": "PPFC", "units": "10", "avg_nav": "60"}],
        SCHEMAS["mf_holdings"],
    )
    data = load()
    assert data.mf_holdings.iloc[0]["isin"] == "INF879O01019"


def test_side_normalised(isolated_portfolio_data: Path) -> None:
    _write_csv(
        isolated_portfolio_data / "stock_transactions.csv",
        [
            {"date": "2024-01-01", "symbol": "X.NS", "exchange": "NSE",
             "side": "BUY", "quantity": "1", "price": "100", "charges": "0", "notes": ""},
            {"date": "2024-02-01", "symbol": "X.NS", "exchange": "NSE",
             "side": "Sell", "quantity": "1", "price": "120", "charges": "0", "notes": ""},
        ],
        SCHEMAS["stock_transactions"],
    )
    data = load()
    sides = data.stock_transactions["side"].tolist()
    assert sides == ["buy", "sell"]
