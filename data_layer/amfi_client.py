"""AMFI India NAV fetcher. Public, unauthenticated, read-only.

Downloads https://www.amfiindia.com/spages/NAVAll.txt, parses the semicolon-
delimited format, and returns `{isin: {nav, date, scheme_name}}`. No credentials,
no personal data, no writes to AMFI.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

import requests

from utils.logging import get_logger

log = get_logger(__name__)

DEFAULT_URL = os.environ.get("AMFI_NAV_URL", "https://www.amfiindia.com/spages/NAVAll.txt")


@dataclass(frozen=True)
class NavRecord:
    isin: str
    scheme_code: str
    scheme_name: str
    nav: float
    date: str  # ISO YYYY-MM-DD


def fetch_all_navs(url: str = DEFAULT_URL, timeout: int = 30) -> dict[str, NavRecord]:
    """Return `{isin: NavRecord}`. Schemes with no ISIN are skipped.

    Each record is keyed by ISIN (growth *and* dividend variants are separate rows
    in the source, each with its own ISIN).
    """
    try:
        r = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Cannot reach AMFI at {url}: {exc}") from exc
    if r.status_code != 200:
        raise RuntimeError(f"AMFI returned HTTP {r.status_code}")

    out: dict[str, NavRecord] = {}
    for line in r.text.splitlines():
        line = line.strip()
        if not line or ";" not in line or line.startswith("Scheme Code"):
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6:
            continue
        # Format: scheme_code;isin_growth;isin_div;scheme_name;nav;date
        scheme_code, isin_g, isin_d, scheme_name, nav_s, date_s = parts[:6]
        if not scheme_code.isdigit():
            continue
        nav = _safe_float(nav_s)
        if nav is None:
            continue
        date_iso = _parse_amfi_date(date_s)
        for isin in (isin_g, isin_d):
            isin = isin.strip().upper()
            if isin and isin != "-":
                out[isin] = NavRecord(
                    isin=isin,
                    scheme_code=scheme_code,
                    scheme_name=scheme_name,
                    nav=nav,
                    date=date_iso,
                )
    log.info("AMFI: parsed %d NAV records", len(out))
    return out


def _safe_float(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse_amfi_date(s: str) -> str:
    """AMFI date format is '19-Apr-2026'. Fall back to today on failure."""
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return datetime.utcnow().date().isoformat()
