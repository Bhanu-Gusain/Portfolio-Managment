"""Read/write portfolio holdings + stocks_master.

Holdings carry an `asset_type` discriminator: `stock` (default), `mutual_fund`, or `etf`.
MFs use ISIN as the symbol (e.g. INF879O01019); stocks use yfinance tickers (e.g. RELIANCE.NS).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from db.repositories import audit_repo
from db.session import get_conn
from utils.time import now_iso


@dataclass(frozen=True)
class Holding:
    id: int
    symbol: str
    quantity: float
    avg_cost: float
    asset_type: str
    uploaded_at: str


def upsert_stock(
    symbol: str,
    name: str,
    sector: str | None = None,
    industry: str | None = None,
    asset_type: str = "stock",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stocks_master (symbol, name, sector, industry, asset_type, added_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
              name=excluded.name,
              sector=COALESCE(excluded.sector, stocks_master.sector),
              industry=COALESCE(excluded.industry, stocks_master.industry),
              asset_type=excluded.asset_type
            """,
            (symbol, name, sector, industry, asset_type, now_iso()),
        )


def replace_holdings(holdings: Iterable[tuple]) -> int:
    """Replace all holdings atomically.

    Each tuple may be either:
      (symbol, quantity, avg_cost)                — asset_type defaults to 'stock'
      (symbol, quantity, avg_cost, asset_type)    — explicit
    """
    ts = now_iso()
    rows: list[tuple] = []
    for h in holdings:
        if len(h) == 3:
            s, q, c = h
            t = "stock"
        elif len(h) == 4:
            s, q, c, t = h
        else:
            raise ValueError(f"Holding tuple must be 3 or 4 items, got: {h!r}")
        rows.append((s, q, c, t, ts))
    with get_conn() as conn:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM portfolio_holdings")
        conn.executemany(
            """
            INSERT INTO portfolio_holdings (symbol, quantity, avg_cost, asset_type, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.execute("COMMIT")
    audit_repo.log("holdings_replaced", f"count={len(rows)}")
    return len(rows)


def list_holdings() -> list[Holding]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol, quantity, avg_cost,
                   COALESCE(asset_type, 'stock') AS asset_type,
                   uploaded_at
            FROM portfolio_holdings ORDER BY symbol
            """
        ).fetchall()
        return [Holding(**dict(r)) for r in rows]


def list_symbols(asset_type: str | None = None) -> list[str]:
    sql = "SELECT DISTINCT symbol FROM portfolio_holdings"
    params: tuple = ()
    if asset_type:
        sql += " WHERE COALESCE(asset_type,'stock')=?"
        params = (asset_type,)
    sql += " ORDER BY symbol"
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [r["symbol"] for r in rows]


def get_stock_meta(symbol: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT symbol, name, sector, industry,
                   COALESCE(asset_type,'stock') AS asset_type
            FROM stocks_master WHERE symbol=?
            """,
            (symbol,),
        ).fetchone()
        return dict(row) if row else None


def list_all_stock_meta() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT symbol, name, sector, industry,
                   COALESCE(asset_type,'stock') AS asset_type
            FROM stocks_master ORDER BY symbol
            """
        ).fetchall()
        return [dict(r) for r in rows]
