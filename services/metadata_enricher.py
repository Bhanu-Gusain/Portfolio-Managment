"""Per-symbol metadata (sector + market-cap in INR) via yfinance `.info`.

Cached to `portfolio_data/.cache/metadata.parquet` with a 7-day TTL. Offline
fetches are never fatal — missing rows come back with NaN sector/mcap and
the caller buckets them as "Uncategorised".
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from utils.config import PROJECT_ROOT, get_settings
from utils.logging import get_logger

log = get_logger(__name__)

CACHE_NAME = "metadata.parquet"
TTL_DAYS = 7


def _cache_path() -> Path:
    return get_settings().cache_dir / CACHE_NAME


def _load_cache() -> pd.DataFrame:
    p = _cache_path()
    if not p.exists():
        return pd.DataFrame(columns=["symbol", "sector", "industry", "marketcap", "fetched_at"])
    try:
        return pd.read_parquet(p)
    except Exception as exc:
        log.warning("metadata cache unreadable (%s) — ignoring", exc)
        return pd.DataFrame(columns=["symbol", "sector", "industry", "marketcap", "fetched_at"])


def _save_cache(df: pd.DataFrame) -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def _fresh(row: pd.Series) -> bool:
    ts = row.get("fetched_at")
    if pd.isna(ts):
        return False
    return (datetime.utcnow() - pd.to_datetime(ts)) < timedelta(days=TTL_DAYS)


def enrich(symbols: list[str], *, suffix: str = ".NS") -> pd.DataFrame:
    """Return a DataFrame indexed by bare symbol with sector + marketcap columns.

    Reads from cache when fresh, fetches the rest from yfinance. Never raises
    on network errors — unresolved symbols just get NaN.
    """
    symbols = [s.strip().upper() for s in symbols if s and isinstance(s, str)]
    symbols = sorted(set(symbols))
    if not symbols:
        return pd.DataFrame(columns=["symbol", "sector", "industry", "marketcap"])

    cache = _load_cache()
    if not cache.empty:
        cache = cache.drop_duplicates(subset=["symbol"], keep="last")

    needed: list[str] = []
    for s in symbols:
        row = cache[cache["symbol"] == s]
        if row.empty or not _fresh(row.iloc[0]):
            needed.append(s)

    if needed:
        fetched = _fetch(needed, suffix=suffix)
        if not fetched.empty:
            cache = pd.concat([cache[~cache["symbol"].isin(fetched["symbol"])], fetched],
                              ignore_index=True)
            _save_cache(cache)

    return cache[cache["symbol"].isin(symbols)].reset_index(drop=True)


def _fetch(symbols: list[str], *, suffix: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed — skipping metadata enrichment")
        return pd.DataFrame()

    rows: list[dict] = []
    now = datetime.utcnow().isoformat(timespec="seconds")
    for s in symbols:
        ticker_id = s if "." in s else f"{s}{suffix}"
        try:
            info = yf.Ticker(ticker_id).info or {}
        except Exception as exc:
            log.debug("yfinance .info failed for %s: %s", ticker_id, exc)
            info = {}
        rows.append({
            "symbol": s,
            "sector": info.get("sector") or "",
            "industry": info.get("industry") or "",
            "marketcap": info.get("marketCap") or float("nan"),
            "fetched_at": now,
        })
    return pd.DataFrame(rows)


# ---------- bucketing helpers ----------

# Approximate SEBI cut-offs: top 100 by mcap ~ ≥ ₹1 lakh crore, 101-250 ~ ₹25k-1L cr.
LARGE_CAP_THRESHOLD_INR = 1_00_000 * 1_00_00_000   # ₹1,00,000 crore = 1e12
MID_CAP_THRESHOLD_INR = 25_000 * 1_00_00_000       # ₹25,000 crore = 2.5e11


def market_cap_bucket(mcap_inr: float | None) -> str:
    if mcap_inr is None or pd.isna(mcap_inr) or mcap_inr <= 0:
        return "Uncategorised"
    if mcap_inr >= LARGE_CAP_THRESHOLD_INR:
        return "Large cap"
    if mcap_inr >= MID_CAP_THRESHOLD_INR:
        return "Mid cap"
    return "Small cap"


def _load_index(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return set()
    return {str(s).strip().upper() for s in df["symbol"] if pd.notna(s)}


def index_bucket(symbol: str, *, data_dir: Path | None = None) -> str:
    data_dir = data_dir or (PROJECT_ROOT / "data")
    sym = str(symbol).strip().upper()
    if sym in _load_index(data_dir / "nifty50.csv"):
        return "Nifty 50"
    if sym in _load_index(data_dir / "niftynext50.csv"):
        return "Nifty Next 50"
    return "Other"
