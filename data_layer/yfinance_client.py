"""Thin yfinance wrapper. Batch OHLCV + per-symbol info. Fail loud on errors."""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from utils.logging import get_logger

log = get_logger(__name__)


def fetch_ohlcv(symbols: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Batch download. Returns {symbol: df with columns date, open, high, low, close, volume}."""
    if not symbols:
        return {}

    log.info("Fetching OHLCV for %d symbols (period=%s)", len(symbols), period)
    raw = yf.download(
        tickers=" ".join(symbols),
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        log.warning("yfinance returned empty result for %s", symbols)
        return out

    if len(symbols) == 1:
        df = raw.copy()
        out[symbols[0]] = _normalise(df)
        return out

    for sym in symbols:
        if sym not in raw.columns.get_level_values(0):
            log.warning("No data returned for %s", sym)
            continue
        df = raw[sym].copy()
        out[sym] = _normalise(df)
    return out


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(how="all")
    if df.empty:
        return df
    df = df.reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    rename = {"adj close": "adj_close"}
    df = df.rename(columns=rename)
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    keep = ["date", "open", "high", "low", "close", "volume"]
    return df[keep].dropna()


def fetch_info(symbol: str) -> dict:
    """Return raw fundamentals dict from yfinance Ticker.info. Best-effort."""
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
    except Exception as exc:
        log.warning("yfinance info failed for %s: %s", symbol, exc)
        return {}

    def _ratio(key: str) -> float | None:
        v = info.get(key)
        return float(v) if v is not None else None

    return {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "roe": _percent(info.get("returnOnEquity")),
        "sales_growth_3y": _percent(info.get("revenueGrowth")),
        "debt_to_equity": _scaled_de(info.get("debtToEquity")),
        "pe": _ratio("trailingPE"),
        "market_cap": _ratio("marketCap"),
    }


def _percent(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return None


def _scaled_de(value) -> float | None:
    """yfinance returns debtToEquity as a raw number (e.g. 85 for 0.85)."""
    if value is None:
        return None
    try:
        v = float(value)
        return v / 100.0 if v > 5 else v
    except (TypeError, ValueError):
        return None
