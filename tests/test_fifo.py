"""Tests for services.fifo."""
from __future__ import annotations

import pandas as pd

from services.fifo import compute_realised, fy_label


def test_empty_input() -> None:
    out = compute_realised(pd.DataFrame(), asset_col="symbol", qty_col="quantity", price_col="price")
    assert out.empty


def test_single_buy_sell_fifo() -> None:
    txns = pd.DataFrame([
        {"date": "2024-01-01", "symbol": "X", "side": "buy", "quantity": 10, "price": 100.0, "charges": 0},
        {"date": "2024-02-01", "symbol": "X", "side": "sell", "quantity": 4, "price": 120.0, "charges": 0},
    ])
    out = compute_realised(txns, asset_col="symbol", qty_col="quantity", price_col="price")
    assert len(out) == 1
    assert out.iloc[0]["quantity"] == 4
    assert out.iloc[0]["gain"] == 80.0  # (120-100)*4


def test_fifo_across_lots() -> None:
    txns = pd.DataFrame([
        {"date": "2023-01-01", "symbol": "X", "side": "buy", "quantity": 5, "price": 100.0, "charges": 0},
        {"date": "2023-06-01", "symbol": "X", "side": "buy", "quantity": 5, "price": 200.0, "charges": 0},
        {"date": "2023-12-01", "symbol": "X", "side": "sell", "quantity": 7, "price": 250.0, "charges": 0},
    ])
    out = compute_realised(txns, asset_col="symbol", qty_col="quantity", price_col="price")
    # First lot fully consumed: 5 * (250-100) = 750
    # Second lot partial 2: 2 * (250-200) = 100
    gains = out.sort_values("buy_date")["gain"].tolist()
    assert gains == [750.0, 100.0]


def test_charges_allocated_proportionally() -> None:
    txns = pd.DataFrame([
        {"date": "2023-01-01", "symbol": "X", "side": "buy", "quantity": 10, "price": 100.0, "charges": 0},
        {"date": "2023-12-01", "symbol": "X", "side": "sell", "quantity": 10, "price": 110.0, "charges": 20.0},
    ])
    out = compute_realised(txns, asset_col="symbol", qty_col="quantity", price_col="price")
    assert out.iloc[0]["charges_allocated"] == 20.0
    assert out.iloc[0]["gain"] == 10 * 10 - 20.0  # 100 - 20


def test_multi_asset() -> None:
    txns = pd.DataFrame([
        {"date": "2024-01-01", "symbol": "A", "side": "buy", "quantity": 1, "price": 10.0, "charges": 0},
        {"date": "2024-01-01", "symbol": "B", "side": "buy", "quantity": 1, "price": 20.0, "charges": 0},
        {"date": "2024-02-01", "symbol": "A", "side": "sell", "quantity": 1, "price": 15.0, "charges": 0},
    ])
    out = compute_realised(txns, asset_col="symbol", qty_col="quantity", price_col="price")
    assert len(out) == 1
    assert out.iloc[0]["asset"] == "A"


def test_fy_label() -> None:
    assert fy_label("2024-04-01") == "FY24-25"
    assert fy_label("2025-03-31") == "FY24-25"
    assert fy_label("2025-04-01") == "FY25-26"
    assert fy_label("2024-12-15") == "FY24-25"
