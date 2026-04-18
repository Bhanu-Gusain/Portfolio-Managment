"""Tests for services.price_fetcher — focused on cache + AMFI parsing (network-mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from services import price_fetcher


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200
    def raise_for_status(self) -> None:  # noqa: D401
        return None


SAMPLE_AMFI = """Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)

122639;INF879O01019;-;Parag Parikh Flexi Cap Fund Direct Growth;72.5000;18-Apr-2026
"""


def test_mf_navs_parses_and_caches(isolated_portfolio_data: Path) -> None:
    with patch("services.price_fetcher.requests.get", return_value=_FakeResponse(SAMPLE_AMFI)):
        result = price_fetcher.fetch_all([], ["INF879O01019"], benchmark=None)
    assert len(result.mf_prices) == 1
    row = result.mf_prices.iloc[0]
    assert row["nav"] == 72.5
    assert row["category"] == "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)"

    # Second call with no network — should come from cache
    with patch("services.price_fetcher.requests.get", side_effect=AssertionError("should not be called")):
        result2 = price_fetcher.fetch_all([], ["INF879O01019"], benchmark=None)
    assert len(result2.mf_prices) == 1


def test_clear_today_cache(isolated_portfolio_data: Path) -> None:
    from datetime import date
    cache_dir = isolated_portfolio_data / ".cache"
    (cache_dir / f"yfinance_prices_{date.today().isoformat()}.parquet").write_bytes(b"\x00")
    (cache_dir / "yfinance_prices_2020-01-01.parquet").write_bytes(b"\x00")
    n = price_fetcher.clear_today_cache()
    assert n == 1
    assert (cache_dir / "yfinance_prices_2020-01-01.parquet").exists()


def test_empty_inputs_no_network(isolated_portfolio_data: Path) -> None:
    with patch("services.price_fetcher.requests.get", side_effect=AssertionError("should not be called")):
        with patch("services.price_fetcher.yf.download", side_effect=AssertionError("should not be called")):
            result = price_fetcher.fetch_all([], [], benchmark=None)
    assert result.stock_prices.empty
    assert result.mf_prices.empty
