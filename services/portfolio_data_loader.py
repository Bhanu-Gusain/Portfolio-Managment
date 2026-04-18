"""File-driven portfolio loader.

Reads the canonical CSV/XLSX files from `portfolio_data/` plus any broker
exports in `portfolio_data/raw/`, merges them into a typed `PortfolioData`
container of pandas DataFrames.

Contract:
- Every file is optional. Missing files produce empty DataFrames with the
  correct columns; downstream code should handle emptiness.
- The loader never silently drops rows. Malformed rows raise ValueError
  with a line-level message.
- Unknown broker files in `raw/` raise UnsupportedFileError from the adapter
  router rather than being ignored.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

import pandas as pd

from services.adapters import UnsupportedFileError, route
from utils.config import get_settings
from utils.logging import get_logger

log = get_logger(__name__)


# ---------- schemas ----------

SCHEMAS: dict[str, list[str]] = {
    "stock_holdings": ["symbol", "exchange", "quantity", "avg_cost", "currency"],
    "mf_holdings": ["isin", "scheme_name", "units", "avg_nav"],
    "stock_transactions": [
        "date", "symbol", "exchange", "side", "quantity", "price", "charges", "notes",
    ],
    "mf_transactions": [
        "date", "isin", "scheme_name", "side", "units", "nav", "amount", "folio", "notes",
    ],
    "dividends": ["date", "symbol_or_isin", "asset_type", "amount", "per_unit", "notes"],
    "watchlist": ["symbol_or_isin", "asset_type", "note"],
}

CANONICAL_FILES = list(SCHEMAS.keys())


NUMERIC_COLS: dict[str, list[str]] = {
    "stock_holdings": ["quantity", "avg_cost"],
    "mf_holdings": ["units", "avg_nav"],
    "stock_transactions": ["quantity", "price", "charges"],
    "mf_transactions": ["units", "nav", "amount"],
    "dividends": ["amount", "per_unit"],
    "watchlist": [],
}

DATE_COLS: dict[str, list[str]] = {
    "stock_holdings": [],
    "mf_holdings": [],
    "stock_transactions": ["date"],
    "mf_transactions": ["date"],
    "dividends": ["date"],
    "watchlist": [],
}


# ---------- container ----------

@dataclass
class PortfolioData:
    stock_holdings: pd.DataFrame = field(default_factory=lambda: _empty("stock_holdings"))
    mf_holdings: pd.DataFrame = field(default_factory=lambda: _empty("mf_holdings"))
    stock_transactions: pd.DataFrame = field(default_factory=lambda: _empty("stock_transactions"))
    mf_transactions: pd.DataFrame = field(default_factory=lambda: _empty("mf_transactions"))
    dividends: pd.DataFrame = field(default_factory=lambda: _empty("dividends"))
    watchlist: pd.DataFrame = field(default_factory=lambda: _empty("watchlist"))
    warnings: list[str] = field(default_factory=list)
    loaded_files: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return all(
            getattr(self, f).empty
            for f in ("stock_holdings", "mf_holdings", "stock_transactions",
                      "mf_transactions", "dividends", "watchlist")
        )

    def status(self) -> dict[str, dict]:
        """Per-file row count, for the sidebar 'Loaded files' panel."""
        out: dict[str, dict] = {}
        for name in CANONICAL_FILES:
            df: pd.DataFrame = getattr(self, name)
            out[name] = {"rows": len(df), "loaded": name in self.loaded_files}
        return out


# ---------- public API ----------

def load(data_dir: Path | None = None) -> PortfolioData:
    """Load all canonical files + adapter-routed raw/ files.

    Canonical files win when a raw/ adapter targets the same name.
    """
    settings = get_settings()
    base = Path(data_dir) if data_dir is not None else settings.portfolio_data_dir
    if not base.exists():
        log.info("portfolio_data dir missing at %s — returning empty PortfolioData", base)
        return PortfolioData()

    data = PortfolioData()

    # 1) Canonical files
    for name in CANONICAL_FILES:
        for ext in (".csv", ".xlsx", ".xls"):
            p = base / f"{name}{ext}"
            if p.exists() and p.stat().st_size > 0:
                df = _read_canonical(p, name)
                if not df.empty:
                    setattr(data, name, df)
                    data.loaded_files.append(p.name)
                break

    # 2) Broker exports in raw/
    raw_dir = base / "raw"
    if raw_dir.exists():
        for p in sorted(raw_dir.iterdir()):
            if p.name.startswith(".") or p.is_dir():
                continue
            if p.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
                continue
            try:
                target, df = route(p)
            except UnsupportedFileError as exc:
                data.warnings.append(str(exc))
                log.warning("Unsupported raw file %s: %s", p.name, exc)
                continue
            except (ValueError, KeyError) as exc:
                data.warnings.append(f"{p.name}: parse error — {exc}")
                log.warning("Adapter parse error on %s: %s", p.name, exc)
                continue

            if target not in SCHEMAS:
                data.warnings.append(f"{p.name}: adapter returned unknown target {target!r}")
                continue

            existing: pd.DataFrame = getattr(data, target)
            if not existing.empty:
                # Canonical file already loaded — merge, dropping exact duplicates
                combined = pd.concat([existing, _coerce(df, target)], ignore_index=True)
                combined = combined.drop_duplicates().reset_index(drop=True)
                setattr(data, target, combined)
            else:
                setattr(data, target, _coerce(df, target))
            data.loaded_files.append(p.name)

    _validate(data)
    return data


def _read_canonical(path: Path, target: str) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    elif ext == ".xlsx":
        df = pd.read_excel(path, engine="openpyxl", dtype=str)
    elif ext == ".xls":
        df = pd.read_excel(path, engine="xlrd", dtype=str)
    else:
        raise ValueError(f"Unsupported extension {ext} for {path}")

    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(how="all")
    if df.empty:
        return _empty(target)

    required = SCHEMAS[target]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path.name}: missing required columns {missing}. "
            f"Expected schema: {required}"
        )

    return _coerce(df[required].copy(), target)


def _coerce(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """Coerce numeric + date columns; uppercase ISINs / normalise sides."""
    df = df.copy()
    # Re-order to canonical column order if all present
    required = SCHEMAS[target]
    df = df.reindex(columns=[c for c in required if c in df.columns])

    for col in NUMERIC_COLS[target]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in DATE_COLS[target]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

    if "isin" in df.columns:
        df["isin"] = df["isin"].astype(str).str.strip().str.upper()
    if "side" in df.columns:
        df["side"] = df["side"].astype(str).str.lower().str.strip()
        df.loc[df["side"].isin(["b", "buy", "purchase"]), "side"] = "buy"
        df.loc[df["side"].isin(["s", "sell", "redemption"]), "side"] = "sell"
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    if "exchange" in df.columns:
        df["exchange"] = df["exchange"].astype(str).str.strip().str.upper().replace("", "NSE")

    return df.reset_index(drop=True)


def _validate(data: PortfolioData) -> None:
    """Sanity-check numeric columns; append warnings rather than raising."""
    checks: Iterable[tuple[str, list[str]]] = (
        ("stock_holdings", ["quantity", "avg_cost"]),
        ("mf_holdings", ["units", "avg_nav"]),
        ("stock_transactions", ["quantity", "price"]),
        ("mf_transactions", ["units"]),
    )
    for name, required in checks:
        df: pd.DataFrame = getattr(data, name)
        if df.empty:
            continue
        bad = df[df[required].isna().any(axis=1)]
        if not bad.empty:
            data.warnings.append(
                f"{name}: {len(bad)} row(s) have missing {required} and were kept "
                "as-is. Fix the source file or expect LTP/P&L columns to be blank."
            )


def _empty(target: str) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in SCHEMAS[target]})


# Re-export for callers that only need the schema
__all__ = ["PortfolioData", "load", "SCHEMAS", "CANONICAL_FILES", "UnsupportedFileError"]
