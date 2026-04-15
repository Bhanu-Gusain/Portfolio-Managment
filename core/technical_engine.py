"""Technical indicators + trend classification.

Uses pandas-ta when available, else hand-rolled EMA/RSI/MACD. Pandas-ta sometimes breaks on numpy>=2 — keeping a fallback so the pipeline cannot silently crash.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class TechnicalSnapshot:
    date: str
    close: float
    ema21: float | None
    ema50: float | None
    ema200: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    high_52w: float
    low_52w: float
    trend_label: str
    is_breakout: int

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "close": self.close,
            "ema21": self.ema21,
            "ema50": self.ema50,
            "ema200": self.ema200,
            "rsi14": self.rsi14,
            "macd": self.macd,
            "macd_signal": self.macd_signal,
            "macd_hist": self.macd_hist,
            "high_52w": self.high_52w,
            "low_52w": self.low_52w,
            "trend_label": self.trend_label,
            "is_breakout": self.is_breakout,
        }


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = _ema(series, fast)
    slow_ema = _ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _classify_trend(close: float, ema21: float | None, ema50: float | None, ema200: float | None, rsi: float | None) -> str:
    if ema21 is None or ema50 is None or ema200 is None:
        return "weak"
    if close > ema21 > ema50 > ema200 and rsi is not None and 50 < rsi < 75:
        return "strong_up"
    if close > ema50 > ema200:
        return "up"
    if close < ema200 and ema50 < ema200:
        return "down"
    return "weak"


def compute(df: pd.DataFrame) -> TechnicalSnapshot:
    """Compute the latest snapshot from a DataFrame with at least a 'close' and 'date' column.

    Index can be the date or a 'date' column. Requires >= 30 rows for any meaningful output;
    raises ValueError below 30.
    """
    if df is None or df.empty:
        raise ValueError("Empty OHLCV DataFrame")

    if "close" not in df.columns:
        raise ValueError("DataFrame missing 'close' column")

    if len(df) < 30:
        raise ValueError(f"Need >= 30 rows, got {len(df)}")

    work = df.copy()
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"])
        work = work.sort_values("date").reset_index(drop=True)
    else:
        work = work.sort_index().reset_index(drop=True)

    close = work["close"].astype(float)

    ema21 = _ema(close, 21)
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    rsi = _rsi(close, 14)
    macd_line, macd_signal, macd_hist = _macd(close)

    last_idx = len(work) - 1
    last_close = float(close.iloc[last_idx])

    window_52w = work.tail(252)
    high_52w = float(window_52w["high"].max() if "high" in window_52w.columns else window_52w["close"].max())
    low_52w = float(window_52w["low"].min() if "low" in window_52w.columns else window_52w["close"].min())

    def _last(series: pd.Series) -> float | None:
        v = series.iloc[last_idx]
        if pd.isna(v):
            return None
        return float(v)

    e21 = _last(ema21)
    e50 = _last(ema50)
    e200 = _last(ema200) if len(work) >= 200 else None
    r14 = _last(rsi)

    trend = _classify_trend(last_close, e21, e50, e200, r14)
    breakout = int(last_close >= 0.95 * high_52w)

    if "date" in work.columns:
        last_date = str(work["date"].iloc[last_idx].date())
    else:
        last_date = str(work.index[last_idx])

    return TechnicalSnapshot(
        date=last_date,
        close=last_close,
        ema21=e21,
        ema50=e50,
        ema200=e200,
        rsi14=r14,
        macd=_last(macd_line),
        macd_signal=_last(macd_signal),
        macd_hist=_last(macd_hist),
        high_52w=high_52w,
        low_52w=low_52w,
        trend_label=trend,
        is_breakout=breakout,
    )


def trend_improving(df: pd.DataFrame, lookback: int = 3) -> bool:
    """True iff EMA21 crossed above EMA50 within the last `lookback` bars."""
    if df is None or len(df) < 60:
        return False
    work = df.copy()
    if "date" in work.columns:
        work = work.sort_values("date").reset_index(drop=True)
    close = work["close"].astype(float)
    e21 = _ema(close, 21)
    e50 = _ema(close, 50)
    diff = (e21 - e50).tail(lookback + 1).values
    if len(diff) < 2:
        return False
    return bool(diff[0] <= 0 and diff[-1] > 0)
