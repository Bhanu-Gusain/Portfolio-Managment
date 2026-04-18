"""Performance analytics: XIRR + portfolio value timeseries from transactions.

XIRR is computed via Brent's method on the NPV function, matching Excel's
XIRR. Timeseries reconstruction walks trading days forward, applying each
transaction and marking-to-market with historical close prices.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.optimize import brentq


# ---------- XIRR ----------

def xirr(cashflows: Iterable[tuple[date | datetime | pd.Timestamp | str, float]]) -> float | None:
    """Compute XIRR for a stream of (date, amount) pairs.

    Convention: investments are NEGATIVE, inflows (sales + current value)
    are POSITIVE. Returns a decimal rate (0.15 = 15%) or None if the stream
    can't be solved (all same-sign, no sign change, or root not bracketed).
    """
    cleaned: list[tuple[datetime, float]] = []
    for d, amt in cashflows:
        ts = pd.to_datetime(d).to_pydatetime()
        cleaned.append((ts, float(amt)))

    if len(cleaned) < 2:
        return None
    if not any(a > 0 for _, a in cleaned) or not any(a < 0 for _, a in cleaned):
        return None

    cleaned.sort(key=lambda x: x[0])
    t0 = cleaned[0][0]
    years = np.array([(ts - t0).days / 365.0 for ts, _ in cleaned])
    amounts = np.array([a for _, a in cleaned])

    def npv(rate: float) -> float:
        if rate <= -0.999:
            return float("inf")
        return float(np.sum(amounts / (1.0 + rate) ** years))

    # Find a bracket
    lo, hi = -0.99, 10.0
    try:
        npv_lo, npv_hi = npv(lo), npv(hi)
    except (OverflowError, ZeroDivisionError):
        return None
    if npv_lo * npv_hi > 0:
        # Try wider
        for hi_try in (20.0, 100.0):
            npv_hi = npv(hi_try)
            if npv_lo * npv_hi < 0:
                hi = hi_try
                break
        else:
            return None

    try:
        return float(brentq(npv, lo, hi, maxiter=200, xtol=1e-6))
    except (ValueError, RuntimeError):
        return None


# ---------- timeseries reconstruction ----------

def portfolio_value_timeseries(
    stock_transactions: pd.DataFrame,
    mf_transactions: pd.DataFrame,
    stock_history: dict[str, pd.DataFrame],
    mf_history: dict[str, pd.DataFrame],
    mf_isin_to_code: dict[str, str],
) -> pd.DataFrame:
    """Reconstruct daily portfolio value from transactions + historical closes.

    Returns a DataFrame with columns: date, value, invested.

    Approach: build a unified trading-day index from all available history,
    walk forward, track running holdings per symbol/ISIN, value = sum(qty *
    close) on each day.
    """
    all_dates: set[str] = set()
    for df in stock_history.values():
        if not df.empty:
            all_dates.update(df["date"].tolist())
    for df in mf_history.values():
        if not df.empty:
            all_dates.update(df["date"].dt.strftime("%Y-%m-%d").tolist() if df["date"].dtype != object else df["date"].tolist())
    if not all_dates:
        return pd.DataFrame(columns=["date", "value", "invested"])

    idx = pd.to_datetime(sorted(all_dates))
    timeline = pd.DataFrame({"date": idx.strftime("%Y-%m-%d")})

    # Per-symbol close lookup (date → close)
    stock_close: dict[str, dict[str, float]] = {
        sym: dict(zip(df["date"], df["close"]))
        for sym, df in stock_history.items() if not df.empty
    }
    mf_close: dict[str, dict[str, float]] = {}
    for isin, code in mf_isin_to_code.items():
        hist = mf_history.get(code)
        if hist is None or hist.empty:
            continue
        dates = hist["date"].dt.strftime("%Y-%m-%d") if hist["date"].dtype != object else hist["date"]
        mf_close[isin] = dict(zip(dates, hist["nav"]))

    # Transaction events keyed by date
    stock_events: dict[str, list[dict]] = _events_by_date(
        stock_transactions, key_col="symbol", qty_col="quantity", price_col="price",
    )
    mf_events: dict[str, list[dict]] = _events_by_date(
        mf_transactions, key_col="isin", qty_col="units", price_col="nav",
    )

    stock_holdings: dict[str, float] = {}
    mf_holdings: dict[str, float] = {}
    stock_last_price: dict[str, float] = {}
    mf_last_price: dict[str, float] = {}
    invested = 0.0

    out_rows: list[dict] = []
    for d in timeline["date"]:
        for ev in stock_events.get(d, []):
            if ev["side"] == "buy":
                stock_holdings[ev["key"]] = stock_holdings.get(ev["key"], 0.0) + ev["qty"]
                invested += ev["qty"] * ev["price"]
            else:
                stock_holdings[ev["key"]] = stock_holdings.get(ev["key"], 0.0) - ev["qty"]
                invested -= ev["qty"] * ev["price"]
            stock_last_price[ev["key"]] = ev["price"]
        for ev in mf_events.get(d, []):
            if ev["side"] == "buy":
                mf_holdings[ev["key"]] = mf_holdings.get(ev["key"], 0.0) + ev["qty"]
                invested += ev["qty"] * ev["price"]
            else:
                mf_holdings[ev["key"]] = mf_holdings.get(ev["key"], 0.0) - ev["qty"]
                invested -= ev["qty"] * ev["price"]
            mf_last_price[ev["key"]] = ev["price"]

        # Value on this date
        value = 0.0
        for sym, qty in stock_holdings.items():
            if qty <= 0:
                continue
            close = stock_close.get(sym, {}).get(d) or stock_last_price.get(sym)
            if close is not None:
                value += qty * close
                stock_last_price[sym] = close
        for isin, units in mf_holdings.items():
            if units <= 0:
                continue
            nav = mf_close.get(isin, {}).get(d) or mf_last_price.get(isin)
            if nav is not None:
                value += units * nav
                mf_last_price[isin] = nav

        out_rows.append({"date": d, "value": value, "invested": invested})

    return pd.DataFrame(out_rows)


def _events_by_date(
    txns: pd.DataFrame, *, key_col: str, qty_col: str, price_col: str
) -> dict[str, list[dict]]:
    if txns.empty:
        return {}
    out: dict[str, list[dict]] = {}
    for _, row in txns.iterrows():
        d = row.get("date")
        if not d or pd.isna(d):
            continue
        side = str(row.get("side", "")).lower()
        try:
            qty = float(row[qty_col])
            price = float(row[price_col])
        except (TypeError, ValueError):
            continue
        key = str(row[key_col]).strip().upper()
        out.setdefault(str(d), []).append({"key": key, "qty": qty, "price": price, "side": side})
    return out
