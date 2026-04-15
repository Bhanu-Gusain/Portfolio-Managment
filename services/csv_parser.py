"""Tolerant Groww CSV parser. Maps stock names to NSE symbols via data/symbol_map.csv.

Fail loud on unmapped names — never silently drop holdings.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from utils.config import PROJECT_ROOT
from utils.logging import get_logger

log = get_logger(__name__)

SYMBOL_MAP_PATH = PROJECT_ROOT / "data" / "symbol_map.csv"


@dataclass(frozen=True)
class ParsedHolding:
    symbol: str
    name: str
    quantity: float
    avg_cost: float


class UnmappedSymbolError(ValueError):
    pass


def _load_symbol_map() -> dict[str, str]:
    if not SYMBOL_MAP_PATH.exists():
        return {}
    out: dict[str, str] = {}
    with SYMBOL_MAP_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip().lower()
            sym = (row.get("symbol") or "").strip()
            if name and sym:
                out[name] = sym
    return out


def _norm(s: str) -> str:
    return s.strip().lower().replace(".", "").replace(",", "")


def parse_groww_csv(path: Path | str) -> list[ParsedHolding]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    name_to_sym = _load_symbol_map()
    name_to_sym_norm = {_norm(k): v for k, v in name_to_sym.items()}

    rows: list[ParsedHolding] = []
    unmapped: list[str] = []

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV {path} has no header row")
        cols = {c.strip().lower(): c for c in reader.fieldnames}

        name_col = _pick(cols, ["stock name", "name", "symbol"])
        qty_col = _pick(cols, ["quantity", "qty", "shares"])
        cost_col = _pick(cols, ["average buy price", "avg buy price", "average price", "avg cost", "avg. cost", "buy price"])

        if not (name_col and qty_col and cost_col):
            raise ValueError(f"CSV missing required columns. Found: {list(cols)}")

        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name:
                continue
            qty_s = (row.get(qty_col) or "").strip().replace(",", "")
            cost_s = (row.get(cost_col) or "").strip().replace(",", "").replace("₹", "")
            if not qty_s or not cost_s:
                continue
            try:
                qty = float(qty_s)
                cost = float(cost_s)
            except ValueError:
                log.warning("Skipping malformed row: %r", row)
                continue

            sym = name_to_sym_norm.get(_norm(name))
            if not sym:
                unmapped.append(name)
                continue
            rows.append(ParsedHolding(symbol=sym, name=name, quantity=qty, avg_cost=cost))

    if unmapped:
        raise UnmappedSymbolError(
            f"Unmapped stock names: {unmapped}. Add them to data/symbol_map.csv."
        )
    if not rows:
        raise ValueError(f"No valid holdings parsed from {path}")

    return rows


def _pick(cols: dict[str, str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in cols:
            return cols[c]
    return None
