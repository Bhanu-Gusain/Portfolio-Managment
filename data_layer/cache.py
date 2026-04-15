"""SQLite-backed OHLCV cache. Single entry point for the pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from data_layer.yfinance_client import fetch_ohlcv
from db.repositories import prices_repo
from utils.config import get_settings
from utils.logging import get_logger

log = get_logger(__name__)


def get_or_fetch(symbols: list[str], period: str = "1y", force: bool = False) -> dict[str, pd.DataFrame]:
    """Return OHLCV per symbol, fetching only stale ones from yfinance."""
    settings = get_settings()
    max_age = timedelta(hours=settings.cache_max_age_hours)
    now = datetime.now(timezone.utc).date()

    fresh: dict[str, pd.DataFrame] = {}
    stale: list[str] = []

    for sym in symbols:
        latest_date = prices_repo.latest_price_date(sym)
        if force or not latest_date:
            stale.append(sym)
            continue
        try:
            ld = datetime.fromisoformat(latest_date).date()
        except ValueError:
            stale.append(sym)
            continue
        age_days = (now - ld).days
        if age_days >= 1 or age_days * 24 >= max_age.total_seconds() / 3600:
            stale.append(sym)
        else:
            fresh[sym] = prices_repo.load_prices(sym).reset_index().rename(columns={"index": "date"})

    if stale:
        log.info("Cache miss for %d/%d symbols; fetching", len(stale), len(symbols))
        fetched = fetch_ohlcv(stale, period=period)
        for sym, df in fetched.items():
            if df.empty:
                log.warning("Empty OHLCV for %s — skipping cache write", sym)
                continue
            prices_repo.upsert_prices(sym, df)
            fresh[sym] = prices_repo.load_prices(sym).reset_index().rename(columns={"index": "date"})

    return fresh
