"""Fundamentals: yfinance best-effort merged with manual CSV overrides."""
from __future__ import annotations

import csv
from pathlib import Path

from data_layer.yfinance_client import fetch_info
from db.repositories import holdings_repo, prices_repo
from utils.config import PROJECT_ROOT
from utils.logging import get_logger
from utils.time import now_iso

log = get_logger(__name__)

OVERRIDES_PATH = PROJECT_ROOT / "data" / "fundamentals_overrides.csv"


def _load_overrides() -> dict[str, dict]:
    if not OVERRIDES_PATH.exists():
        return {}
    out: dict[str, dict] = {}
    with OVERRIDES_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row["symbol"].strip()
            if not sym:
                continue
            out[sym] = {
                "roe": _to_float(row.get("roe")),
                "sales_growth_3y": _to_float(row.get("sales_growth_3y")),
                "debt_to_equity": _to_float(row.get("debt_to_equity")),
                "pe": _to_float(row.get("pe")),
                "market_cap": _to_float(row.get("market_cap")),
            }
    return out


def _to_float(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def refresh(symbols: list[str]) -> None:
    """Refresh fundamentals for the given symbols. Override CSV always wins per-field."""
    overrides = _load_overrides()
    ts = now_iso()

    for sym in symbols:
        info = fetch_info(sym)
        ovr = overrides.get(sym, {})

        if info.get("name"):
            holdings_repo.upsert_stock(sym, info["name"], info.get("sector"), info.get("industry"))

        merged = {
            "roe": ovr.get("roe") if ovr.get("roe") is not None else info.get("roe"),
            "sales_growth_3y": ovr.get("sales_growth_3y") if ovr.get("sales_growth_3y") is not None else info.get("sales_growth_3y"),
            "debt_to_equity": ovr.get("debt_to_equity") if ovr.get("debt_to_equity") is not None else info.get("debt_to_equity"),
            "pe": ovr.get("pe") if ovr.get("pe") is not None else info.get("pe"),
            "market_cap": ovr.get("market_cap") if ovr.get("market_cap") is not None else info.get("market_cap"),
        }
        any_override = any(ovr.get(k) is not None for k in ("roe", "sales_growth_3y", "debt_to_equity", "pe", "market_cap"))
        source = "override" if any_override else "yfinance"
        prices_repo.upsert_fundamentals(sym, merged, source=source, updated_at=ts)
        log.info("Fundamentals upserted for %s (source=%s)", sym, source)
