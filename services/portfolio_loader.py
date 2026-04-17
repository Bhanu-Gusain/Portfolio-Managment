"""Unified portfolio file loader: CSV, XLSX, XLS.

Accepts any reasonable layout from brokers or hand-typed files and produces
`ParsedHolding` records. Supports both stocks and mutual funds in the same
upload — asset type is either declared in an `asset_type` column or inferred
from columns like `units`/`nav`/`isin`.

Design notes:
- Never silently drops rows. Unmapped stock names raise `UnmappedSymbolError`
  so the user can fix `data/symbol_map.csv`.
- Fails loud on unreadable files and ambiguous schemas.
- No personal data is retained on disk beyond the user's own `data/analysis.db`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from utils.config import PROJECT_ROOT
from utils.logging import get_logger

log = get_logger(__name__)

SYMBOL_MAP_PATH = PROJECT_ROOT / "data" / "symbol_map.csv"
MF_MAP_PATH = PROJECT_ROOT / "data" / "mf_map.csv"

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


@dataclass(frozen=True)
class ParsedHolding:
    symbol: str       # NSE ticker for stocks, ISIN for mutual funds
    name: str
    quantity: float
    avg_cost: float
    asset_type: str   # 'stock' | 'mutual_fund'


class UnmappedSymbolError(ValueError):
    pass


# ---------- public entrypoint ----------

def parse_portfolio_file(path: Path | str) -> list[ParsedHolding]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    df = _read_any(path)
    df = _normalise_columns(df)

    if df.empty:
        raise ValueError(f"File {path.name} contains no data rows.")

    cols = set(df.columns)

    # Try to split into stock rows and MF rows.
    stock_rows, mf_rows = _split_by_asset_type(df, cols)

    holdings: list[ParsedHolding] = []
    unmapped: list[str] = []

    if not stock_rows.empty:
        stock_map_norm = {_norm(k): v for k, v in _load_name_map(SYMBOL_MAP_PATH).items()}
        holdings.extend(_parse_stocks(stock_rows, stock_map_norm, unmapped))

    if not mf_rows.empty:
        mf_map = _load_name_map(MF_MAP_PATH)
        mf_map_norm = {_norm(k): v for k, v in mf_map.items()}
        holdings.extend(_parse_mfs(mf_rows, mf_map_norm))

    if unmapped:
        raise UnmappedSymbolError(
            f"Unmapped stock names: {unmapped}. Add them to data/symbol_map.csv."
        )
    if not holdings:
        raise ValueError(
            f"No valid holdings parsed from {path.name}. "
            "Check column headers — expected at least name/symbol, quantity, and avg cost."
        )
    return holdings


# ---------- legacy alias ----------

def parse_groww_csv(path: Path | str) -> list[ParsedHolding]:
    """Backward-compat shim. Use `parse_portfolio_file` for new code."""
    return parse_portfolio_file(path)


# ---------- IO ----------

def _read_any(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if ext == ".xlsx":
        return pd.read_excel(path, engine="openpyxl", dtype=str)
    if ext == ".xls":
        return pd.read_excel(path, engine="xlrd", dtype=str)
    raise ValueError(f"Unsupported file type: {ext}")


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    # Drop fully-empty rows
    df = df.dropna(how="all")
    # Treat NaN as empty string for dtype=str consistency
    df = df.fillna("")
    return df


def _split_by_asset_type(df: pd.DataFrame, cols: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows into (stock_rows, mf_rows).

    Rules:
    - If `asset_type` column is present: split on its value (stock/mutual_fund/etf).
      ETFs are treated as stocks for pricing purposes.
    - Else, if MF-specific columns are present (units, nav, scheme), treat all as MF.
    - Else, treat all as stocks.
    """
    if "asset_type" in cols:
        at = df["asset_type"].str.lower().str.strip()
        mf_mask = at.isin(["mutual_fund", "mf", "mutualfund", "fund"])
        stock_mask = ~mf_mask  # stock + etf + empty default to stock
        return df[stock_mask], df[mf_mask]

    mf_signals = cols & {"scheme name", "scheme_name", "scheme", "units", "nav", "avg nav", "avg_nav"}
    if mf_signals and not (cols & {"stock name", "symbol", "ticker"}):
        return df.iloc[0:0], df

    return df, df.iloc[0:0]


# ---------- row parsers ----------

def _parse_stocks(
    df: pd.DataFrame, name_to_sym_norm: dict[str, str], unmapped: list[str]
) -> list[ParsedHolding]:
    name_col = _pick(df.columns, ["stock name", "name", "symbol", "ticker", "instrument", "identifier"])
    qty_col = _pick(df.columns, ["quantity", "qty", "shares", "units"])
    cost_col = _pick(df.columns, [
        "average buy price", "avg buy price", "average price",
        "avg cost", "avg. cost", "avg_cost", "buy price", "cost", "price",
    ])
    if not (name_col and qty_col and cost_col):
        raise ValueError(
            f"Stock rows missing required columns. Found: {list(df.columns)}. "
            "Expected name/symbol + quantity + avg cost."
        )

    out: list[ParsedHolding] = []
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name:
            continue
        qty = _to_float(row.get(qty_col))
        cost = _to_float(row.get(cost_col))
        if qty is None or cost is None:
            log.warning("Skipping malformed stock row: %r", dict(row))
            continue

        # If the user already supplied a ticker (contains '.' or looks like ALL CAPS),
        # trust it. Otherwise, resolve via symbol_map.
        sym = _resolve_stock_symbol(name, name_to_sym_norm)
        if not sym:
            unmapped.append(name)
            continue
        out.append(ParsedHolding(symbol=sym, name=name, quantity=qty, avg_cost=cost, asset_type="stock"))
    return out


def _parse_mfs(df: pd.DataFrame, mf_map_norm: dict[str, str]) -> list[ParsedHolding]:
    name_col = _pick(df.columns, ["scheme name", "scheme_name", "scheme", "name", "identifier"])
    isin_col = _pick(df.columns, ["isin", "identifier"])
    qty_col = _pick(df.columns, ["units", "quantity", "qty"])
    cost_col = _pick(df.columns, ["avg nav", "avg_nav", "average nav", "nav", "avg cost", "avg_cost", "cost", "price"])
    if not (qty_col and cost_col and (name_col or isin_col)):
        raise ValueError(
            f"Mutual fund rows missing required columns. Found: {list(df.columns)}. "
            "Expected scheme name or ISIN + units + avg NAV/cost."
        )

    out: list[ParsedHolding] = []
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip() if name_col else ""
        isin = str(row.get(isin_col, "")).strip().upper() if isin_col else ""
        qty = _to_float(row.get(qty_col))
        cost = _to_float(row.get(cost_col))
        if qty is None or cost is None:
            log.warning("Skipping malformed MF row: %r", dict(row))
            continue

        symbol = isin if ISIN_RE.match(isin) else mf_map_norm.get(_norm(name), "")
        if not symbol:
            # Last resort: treat the raw name as the symbol. NAV fetch will fail loudly downstream.
            raise UnmappedSymbolError(
                f"Mutual fund '{name or isin or '<blank>'}' has no ISIN in the file and no entry in data/mf_map.csv."
            )
        if not name:
            name = symbol
        out.append(ParsedHolding(symbol=symbol, name=name, quantity=qty, avg_cost=cost, asset_type="mutual_fund"))
    return out


# ---------- helpers ----------

def _pick(cols, candidates: list[str]) -> str | None:
    colset = set(cols)
    for c in candidates:
        if c in colset:
            return c
    return None


def _to_float(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("₹", "").replace("$", "")
    if not s or s.lower() in ("nan", "none", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower().replace(".", "").replace(",", ""))


def _load_name_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    name_col = _pick(df.columns, ["name", "scheme", "scheme_name"])
    sym_col = _pick(df.columns, ["symbol", "isin", "code"])
    if not (name_col and sym_col):
        return {}
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        sym = str(row[sym_col]).strip()
        if name and sym:
            out[name] = sym
    return out


def _resolve_stock_symbol(name: str, name_to_sym_norm: dict[str, str]) -> str | None:
    # Already a ticker (heuristic: contains '.' like RELIANCE.NS, or is all caps without spaces)
    s = name.strip()
    if "." in s and " " not in s:
        return s.upper()
    if s.isupper() and " " not in s and len(s) <= 15:
        return s if "." in s else f"{s}.NS"
    return name_to_sym_norm.get(_norm(s))
