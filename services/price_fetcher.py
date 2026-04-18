"""Price fetcher with day-granular on-disk parquet cache.

Inputs come from the loader's DataFrames (symbols, ISINs); outputs are tidy
DataFrames the dashboard can consume directly.

Sources:
  - stocks: yfinance batch download (LTP + 3 months history)
  - MF LTP + category: AMFI NAVAll.txt
  - MF history (perf tab only): api.mfapi.in per scheme code

Cache: `portfolio_data/.cache/<source>_<YYYY-MM-DD>.parquet`. Same-day hit →
cached; older → refetch. `refresh=True` force-invalidates the day.

Offline / fetch failure is never fatal — the caller gets an empty frame and a
warning; the dashboard shows LTP as `—`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
import yfinance as yf

from utils.config import get_settings
from utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class PriceResult:
    """Bundle of frames + warnings returned to the dashboard."""
    stock_prices: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=["symbol", "ltp", "prev_close", "day_change_pct",
                     "high_52w", "low_52w", "currency"]
        )
    )
    stock_history: dict[str, pd.DataFrame] = field(default_factory=dict)
    mf_prices: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=["isin", "nav", "scheme_name", "category", "nav_date", "scheme_code"]
        )
    )
    mf_history: dict[str, pd.DataFrame] = field(default_factory=dict)
    benchmark_history: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=["date", "close"])
    )
    warnings: list[str] = field(default_factory=list)


# ---------- public API ----------

def fetch_all(
    stock_symbols: Iterable[str],
    mf_isins: Iterable[str],
    *,
    period: str = "3mo",
    refresh: bool = False,
    benchmark: str | None = "^NSEI",
) -> PriceResult:
    """Fetch stock prices (+ history), MF NAVs (+ AMFI metadata), and benchmark.

    Returns a PriceResult. Never raises — fetch failures show up in .warnings.
    """
    stock_symbols = sorted({s for s in stock_symbols if s})
    mf_isins = sorted({i for i in mf_isins if i})

    result = PriceResult()

    stock_df, stock_hist = _stocks(stock_symbols, period=period, refresh=refresh, warnings=result.warnings)
    result.stock_prices = stock_df
    result.stock_history = stock_hist

    mf_df = _mf_navs(mf_isins, refresh=refresh, warnings=result.warnings)
    result.mf_prices = mf_df

    if benchmark:
        bench_hist = _benchmark(benchmark, period=period, refresh=refresh, warnings=result.warnings)
        result.benchmark_history = bench_hist

    return result


def fetch_mf_history(scheme_codes: Iterable[str], *, refresh: bool = False) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Historical NAV per scheme code (from api.mfapi.in). Used by Performance tab.

    Returns ({scheme_code: DataFrame[date, nav]}, warnings).
    """
    settings = get_settings()
    warnings: list[str] = []
    out: dict[str, pd.DataFrame] = {}
    for code in set(scheme_codes):
        if not code:
            continue
        cache = _cache_path(f"mfapi_{code}")
        df = _read_cache(cache) if not refresh else None
        if df is not None:
            out[code] = df
            continue
        try:
            r = requests.get(f"{settings.mfapi_base_url}/{code}", timeout=15)
            r.raise_for_status()
            payload = r.json()
        except (requests.RequestException, ValueError) as exc:
            warnings.append(f"mfapi.in: scheme {code} failed — {exc}")
            continue
        rows = payload.get("data", [])
        if not rows:
            warnings.append(f"mfapi.in: scheme {code} returned no data")
            continue
        hist = pd.DataFrame(rows)
        hist["date"] = pd.to_datetime(hist["date"], format="%d-%m-%Y", errors="coerce")
        hist["nav"] = pd.to_numeric(hist["nav"], errors="coerce")
        hist = hist.dropna(subset=["date", "nav"]).sort_values("date").reset_index(drop=True)
        _write_cache(cache, hist)
        out[code] = hist
    return out, warnings


def clear_today_cache() -> int:
    """Remove today's cached parquet files. Returns count deleted."""
    settings = get_settings()
    if not settings.cache_dir.exists():
        return 0
    today = date.today().isoformat()
    n = 0
    for p in settings.cache_dir.iterdir():
        if today in p.name and p.suffix == ".parquet":
            p.unlink(missing_ok=True)
            n += 1
    return n


# ---------- stock path ----------

def _stocks(
    symbols: list[str], *, period: str, refresh: bool, warnings: list[str]
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    if not symbols:
        empty = pd.DataFrame(
            columns=["symbol", "ltp", "prev_close", "day_change_pct",
                     "high_52w", "low_52w", "currency"]
        )
        return empty, {}

    cache_prices = _cache_path("yfinance_prices")
    cache_history = _cache_path("yfinance_history")

    prices_cached = _read_cache(cache_prices) if not refresh else None
    history_cached = _read_cache(cache_history) if not refresh else None

    if prices_cached is not None and history_cached is not None:
        cached_syms = set(prices_cached["symbol"])
        if set(symbols).issubset(cached_syms):
            history_map = _split_history_frame(history_cached)
            return prices_cached[prices_cached["symbol"].isin(symbols)].copy(), history_map

    try:
        raw = yf.download(
            tickers=" ".join(symbols),
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception as exc:  # yfinance raises many network-flavoured errors
        warnings.append(f"yfinance fetch failed: {exc}")
        empty = pd.DataFrame(
            columns=["symbol", "ltp", "prev_close", "day_change_pct",
                     "high_52w", "low_52w", "currency"]
        )
        return empty, {}

    prices_rows: list[dict] = []
    history_map: dict[str, pd.DataFrame] = {}
    history_rows_for_cache: list[pd.DataFrame] = []

    if raw is None or raw.empty:
        warnings.append("yfinance returned no data")
        empty = pd.DataFrame(
            columns=["symbol", "ltp", "prev_close", "day_change_pct",
                     "high_52w", "low_52w", "currency"]
        )
        return empty, {}

    for sym in symbols:
        try:
            sub = raw[sym] if len(symbols) > 1 else raw
        except KeyError:
            warnings.append(f"{sym}: no data from yfinance")
            continue
        sub = sub.dropna(how="all")
        if sub.empty:
            warnings.append(f"{sym}: empty history from yfinance")
            continue

        closes = sub["Close"].dropna()
        if closes.empty:
            warnings.append(f"{sym}: no Close column")
            continue

        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
        day_change = ((last - prev) / prev * 100.0) if prev else 0.0
        high_52 = float(sub["High"].max()) if "High" in sub else last
        low_52 = float(sub["Low"].min()) if "Low" in sub else last

        prices_rows.append({
            "symbol": sym,
            "ltp": last,
            "prev_close": prev,
            "day_change_pct": day_change,
            "high_52w": high_52,
            "low_52w": low_52,
            "currency": "INR" if sym.endswith(".NS") or sym.endswith(".BO") else "USD",
        })

        hist = sub.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "close"})
        hist["date"] = pd.to_datetime(hist["date"]).dt.strftime("%Y-%m-%d")
        hist["close"] = pd.to_numeric(hist["close"], errors="coerce")
        hist = hist.dropna().reset_index(drop=True)
        history_map[sym] = hist

        tagged = hist.copy()
        tagged.insert(0, "symbol", sym)
        history_rows_for_cache.append(tagged)

    prices_df = pd.DataFrame(prices_rows)
    _write_cache(cache_prices, prices_df)

    if history_rows_for_cache:
        combined = pd.concat(history_rows_for_cache, ignore_index=True)
        _write_cache(cache_history, combined)

    return prices_df, history_map


def _split_history_frame(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        sym: sub.drop(columns=["symbol"]).reset_index(drop=True)
        for sym, sub in df.groupby("symbol")
    }


# ---------- MF path ----------

def _mf_navs(isins: list[str], *, refresh: bool, warnings: list[str]) -> pd.DataFrame:
    if not isins:
        return pd.DataFrame(
            columns=["isin", "nav", "scheme_name", "category", "nav_date", "scheme_code"]
        )
    cache = _cache_path("amfi")
    cached = _read_cache(cache) if not refresh else None
    if cached is not None and not cached.empty:
        out = cached[cached["isin"].isin(isins)].copy()
        if not out.empty:
            return out

    settings = get_settings()
    try:
        r = requests.get(settings.amfi_nav_url, timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        warnings.append(f"AMFI fetch failed: {exc}")
        return pd.DataFrame(
            columns=["isin", "nav", "scheme_name", "category", "nav_date", "scheme_code"]
        )

    rows: list[dict] = []
    current_category = ""
    for raw in r.text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ";" not in line:
            # Category headers are plain text lines between blocks
            if not line.lower().startswith("scheme code"):
                current_category = line
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        scheme_code, isin_g, isin_d, scheme_name, nav_s, date_s = parts[:6]
        nav_val = _to_float(nav_s)
        if nav_val is None:
            continue
        nav_date = _parse_amfi_date(date_s)
        for isin in (isin_g, isin_d):
            isin_u = (isin or "").strip().upper()
            if isin_u and isin_u != "-":
                rows.append({
                    "isin": isin_u,
                    "nav": nav_val,
                    "scheme_name": scheme_name,
                    "category": current_category,
                    "nav_date": nav_date,
                    "scheme_code": scheme_code,
                })

    full = pd.DataFrame(rows).drop_duplicates(subset=["isin"]).reset_index(drop=True)
    _write_cache(cache, full)
    return full[full["isin"].isin(isins)].copy()


# ---------- benchmark ----------

def _benchmark(ticker: str, *, period: str, refresh: bool, warnings: list[str]) -> pd.DataFrame:
    cache = _cache_path(f"benchmark_{ticker.replace('^', '')}")
    cached = _read_cache(cache) if not refresh else None
    if cached is not None:
        return cached
    try:
        raw = yf.download(
            tickers=ticker, period=period, interval="1d",
            auto_adjust=False, progress=False,
        )
    except Exception as exc:
        warnings.append(f"benchmark {ticker} fetch failed: {exc}")
        return pd.DataFrame(columns=["date", "close"])
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "close"])
    hist = raw.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "close"})
    hist["date"] = pd.to_datetime(hist["date"]).dt.strftime("%Y-%m-%d")
    hist["close"] = pd.to_numeric(hist["close"], errors="coerce")
    hist = hist.dropna().reset_index(drop=True)
    _write_cache(cache, hist)
    return hist


# ---------- cache helpers ----------

def _cache_path(source: str) -> Path:
    settings = get_settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings.cache_dir / f"{source}_{date.today().isoformat()}.parquet"


def _read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        log.warning("cache read failed for %s: %s", path, exc)
        return None


def _write_cache(path: Path, df: pd.DataFrame) -> None:
    try:
        df.to_parquet(path, index=False)
    except Exception as exc:
        log.warning("cache write failed for %s: %s", path, exc)


def _to_float(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse_amfi_date(s: str) -> str:
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return date.today().isoformat()
