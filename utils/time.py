"""NSE trading-day helpers. No business logic — just calendar math."""
from __future__ import annotations

from datetime import date, datetime, timezone


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_weekday(d: date) -> bool:
    return d.weekday() < 5
