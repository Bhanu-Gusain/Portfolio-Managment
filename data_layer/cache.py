"""SQLite-backed price cache. Single entry point for the pipeline.

Routes symbols by asset type:
- Stocks/ETFs → yfinance OHLCV.
- Mutual funds (ISIN) → AMFI NAV. NAV is stored as a single-day OHLC row
  (open=high=low=close=NAV, volume=0) so the rest of the pipeline needs no change.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from data_layer.amfi_client import fetch_all_navs
from data_layer.yfinance_client import fetch_ohlcv
from db.repositories import holdings_repo, prices_repo
from utils.config import get_settings
from utils.logging import get_logger

log = get_logger(__name__)


def get_or_fetch(symbols: list[str], period: str = "1y", force: bool = False) -> dict[str, pd.DataFrame]:
    """Return OHLCV per symbol, fetching only stale ones."""
    settings = get_settings()
    max_age = timedelta(hours=settings.cache_max_age_hours)
    now = datetime.now(timezone.utc).date()

    stock_syms, mf_syms = _split_by_type(symbols)

    fresh: dict[str, pd.DataFrame] = {}
    stale_stocks: list[str] = []
    stale_mfs: list[str] = []

    for sym in stock_syms:
        if _is_stale(sym, now, max_age, force):
            stale_stocks.append(sym)
        else:
            fresh[sym] = _load_df(sym)

    for sym in mf_syms:
        if _is_stale(sym, now, max_age, force):
            stale_mfs.append(sym)
        else:
            fresh[sym] = _load_df(sym)

    if stale_stocks:
        log.info("Cache miss for %d stock symbols; fetching from yfinance", len(stale_stocks))
        fetched = fetch_ohlcv(stale_stocks, period=period)
        for sym, df in fetched.items():
            if df.empty:
                log.warning("Empty OHLCV for %s", sym)
                continue
            prices_repo.upsert_prices(sym, df)
            fresh[sym] = _load_df(sym)

    if stale_mfs:
        log.info("Cache miss for %d MFs; fetching from AMFI", len(stale_mfs))
        try:
            nav_map = fetch_all_navs()
        except RuntimeError as exc:
            log.warning("AMFI fetch failed: %s", exc)
            nav_map = {}
        for isin in stale_mfs:
            rec = nav_map.get(isin)
            if rec is None:
                log.warning("No NAV found on AMFI for ISIN %s", isin)
                continue
            row = pd.DataFrame([{
                "date": rec.date,
                "open": rec.nav, "high": rec.nav, "low": rec.nav,
                "close": rec.nav, "volume": 0,
            }])
            prices_repo.upsert_prices(isin, row)
            # Make sure a master row exists with the scheme name.
            existing = holdings_repo.get_stock_meta(isin)
            if not existing:
                holdings_repo.upsert_stock(isin, rec.scheme_name, asset_type="mutual_fund")
            else:
                holdings_repo.upsert_stock(isin, existing.get("name") or rec.scheme_name, asset_type="mutual_fund")
            fresh[isin] = _load_df(isin)

    return fresh


def _split_by_type(symbols: list[str]) -> tuple[list[str], list[str]]:
    stocks: list[str] = []
    mfs: list[str] = []
    for sym in symbols:
        meta = holdings_repo.get_stock_meta(sym) or {}
        asset_type = meta.get("asset_type") or _guess_asset_type(sym)
        (mfs if asset_type == "mutual_fund" else stocks).append(sym)
    return stocks, mfs


def _guess_asset_type(sym: str) -> str:
    """ISIN-like symbols (12 chars, country code prefix) → mutual_fund. Else stock."""
    s = sym.strip().upper()
    if len(s) == 12 and s[:2].isalpha() and s[-1].isdigit():
        return "mutual_fund"
    return "stock"


def _is_stale(sym: str, now, max_age: timedelta, force: bool) -> bool:
    if force:
        return True
    latest_date = prices_repo.latest_price_date(sym)
    if not latest_date:
        return True
    try:
        ld = datetime.fromisoformat(latest_date).date()
    except ValueError:
        return True
    age_days = (now - ld).days
    if age_days >= 1:
        return True
    return age_days * 24 >= max_age.total_seconds() / 3600


def _load_df(sym: str) -> pd.DataFrame:
    return prices_repo.load_prices(sym).reset_index().rename(columns={"index": "date"})
