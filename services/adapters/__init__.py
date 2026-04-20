"""Broker export adapters.

Every adapter exposes:
    - NAME: str (module-level)
    - matches(path: Path) -> bool
    - parse(path: Path) -> pd.DataFrame | dict[str, pd.DataFrame]
    - TARGET: str  (one of: stock_holdings, mf_holdings, stock_transactions,
                   mf_transactions, dividends, watchlist, or "auto" / "multi")

Adapters that serve a single canonical target return a DataFrame; adapters
that emit rows for multiple targets from one file (e.g. a consolidated
workbook with holdings + transactions) return `dict[target, DataFrame]`.

To register a new adapter, add it to ADAPTERS below.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from services.adapters import groww, kuvera, portfolio_xlsx, zerodha


class UnsupportedFileError(ValueError):
    pass


Adapter = Callable[[Path], pd.DataFrame]


ADAPTERS = [
    portfolio_xlsx,  # first: multi-sheet workbook detection by sheet names
    groww,
    zerodha,
    kuvera,
]


def route(path: Path) -> list[tuple[str, pd.DataFrame]]:
    """Find an adapter that matches `path` and invoke it.

    Returns a list of `(target, dataframe)` pairs. Most adapters yield a
    single pair; a multi-sheet adapter may yield one per canonical target.

    Raises UnsupportedFileError with actionable hint if no adapter matches.
    """
    for adapter in ADAPTERS:
        if not adapter.matches(path):
            continue
        result = adapter.parse(path)
        if isinstance(result, dict):
            return [(t, df) for t, df in result.items()]
        target = result.attrs.get("target") or getattr(adapter, "TARGET", "auto")
        if target in ("auto", "multi"):
            raise UnsupportedFileError(
                f"Adapter {adapter.NAME} could not determine target for "
                f"{path.name}."
            )
        return [(target, result)]
    raise UnsupportedFileError(
        f"Unrecognised broker file `{path.name}`. Either rename it to one of "
        "the canonical names (stock_holdings.csv, mf_holdings.csv, "
        "stock_transactions.csv, mf_transactions.csv, dividends.csv, "
        "watchlist.csv) and move it one level up, add a matching adapter in "
        "services/adapters/, or move the file to portfolio_data/archive/ to "
        "ignore it."
    )
