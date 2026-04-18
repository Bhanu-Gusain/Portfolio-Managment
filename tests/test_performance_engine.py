"""Tests for core.performance_engine."""
from __future__ import annotations

from core.performance_engine import xirr


def test_xirr_simple() -> None:
    # Invest 100 on day 0, get 110 one year later → 10% XIRR
    rate = xirr([("2024-01-01", -100.0), ("2025-01-01", 110.0)])
    assert rate is not None
    assert abs(rate - 0.10) < 0.001


def test_xirr_no_sign_change() -> None:
    assert xirr([("2024-01-01", -100.0), ("2024-06-01", -50.0)]) is None
    assert xirr([("2024-01-01", 100.0), ("2024-06-01", 50.0)]) is None


def test_xirr_too_few() -> None:
    assert xirr([("2024-01-01", -100.0)]) is None


def test_xirr_multiple_flows() -> None:
    # SIP: 1000 every month for 12 months, final value 13000 after 1 year
    import datetime as dt
    cfs = []
    for i in range(12):
        cfs.append((dt.date(2024, i + 1, 1), -1000.0))
    cfs.append((dt.date(2025, 1, 1), 13000.0))
    rate = xirr(cfs)
    assert rate is not None
    assert 0.05 < rate < 0.30  # reasonable SIP return range
