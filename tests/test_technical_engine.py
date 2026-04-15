from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.technical_engine import compute, trend_improving


def _synthetic(trend: str, n: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = 100.0
    if trend == "up":
        prices = base + np.cumsum(rng.normal(0.5, 0.8, n))
    elif trend == "down":
        prices = base + np.cumsum(rng.normal(-0.5, 0.8, n))
    else:
        prices = base + np.cumsum(rng.normal(0.0, 0.5, n))
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": prices,
        "high": prices + 1,
        "low": prices - 1,
        "close": prices,
        "volume": np.full(n, 1000),
    })
    return df


def test_compute_uptrend():
    snap = compute(_synthetic("up"))
    assert snap.trend_label in ("strong_up", "up")
    assert snap.ema21 is not None
    assert snap.high_52w >= snap.close


def test_compute_downtrend():
    snap = compute(_synthetic("down"))
    assert snap.trend_label in ("down", "weak")


def test_compute_short_history_raises():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=10), "close": range(10)})
    with pytest.raises(ValueError):
        compute(df)


def test_trend_improving_detects_cross():
    # Long downtrend then sharp rise — EMA21 must cross above EMA50 within the lookback window.
    falling = np.linspace(100, 50, 60)
    rising = np.linspace(50, 200, 30)
    prices = np.concatenate([falling, rising])
    n = len(prices)
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "close": prices,
        "high": prices + 1, "low": prices - 1, "open": prices, "volume": 1000,
    })
    # Use a wider window so we capture the cross even if it happens a few bars before the end.
    assert trend_improving(df, lookback=25) is True
