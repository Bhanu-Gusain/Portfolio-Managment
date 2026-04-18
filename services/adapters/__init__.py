"""Broker export adapters.

Every adapter exposes:
    - NAME: str (module-level)
    - matches(path: Path) -> bool
    - parse(path: Path) -> pd.DataFrame  (canonical schema for its target file)
    - TARGET: str  (one of: stock_holdings, mf_holdings, stock_transactions,
                   mf_transactions, dividends, watchlist)

To register a new adapter, add it to ADAPTERS below.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from services.adapters import groww, kuvera, zerodha


class UnsupportedFileError(ValueError):
    pass


Adapter = Callable[[Path], pd.DataFrame]


ADAPTERS = [
    groww,
    zerodha,
    kuvera,
]


def route(path: Path) -> tuple[str, pd.DataFrame]:
    """Find an adapter that matches `path` and invoke it.

    Returns `(target, dataframe)` where `target` is the canonical file name
    (without extension): one of stock_holdings, mf_holdings, stock_transactions,
    mf_transactions.

    Raises UnsupportedFileError with actionable hint if no adapter matches.
    """
    for adapter in ADAPTERS:
        if adapter.matches(path):
            df = adapter.parse(path)
            target = df.attrs.get("target") or getattr(adapter, "TARGET", "auto")
            if target == "auto":
                raise UnsupportedFileError(
                    f"Adapter {adapter.NAME} could not determine target for "
                    f"{path.name}."
                )
            return target, df
    raise UnsupportedFileError(
        f"Unrecognised broker file `{path.name}`. Either rename it to one of "
        "the canonical names (stock_holdings.csv, mf_holdings.csv, "
        "stock_transactions.csv, mf_transactions.csv, dividends.csv, "
        "watchlist.csv) and move it one level up, add a matching adapter in "
        "services/adapters/, or move the file to portfolio_data/archive/ to "
        "ignore it."
    )
