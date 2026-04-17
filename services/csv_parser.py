"""Backward-compat shim.

The real loader now lives in `services.portfolio_loader` and supports CSV, XLSX,
and XLS — plus mutual funds alongside stocks. This module re-exports the old
names so existing callers keep working.
"""
from __future__ import annotations

from services.portfolio_loader import (  # noqa: F401
    ParsedHolding,
    UnmappedSymbolError,
    parse_groww_csv,
    parse_portfolio_file,
)

__all__ = [
    "ParsedHolding",
    "UnmappedSymbolError",
    "parse_groww_csv",
    "parse_portfolio_file",
]
