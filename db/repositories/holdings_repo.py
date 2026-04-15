"""Read/write portfolio holdings + stocks_master."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from db.session import get_conn
from utils.time import now_iso


@dataclass(frozen=True)
class Holding:
    id: int
    symbol: str
    quantity: float
    avg_cost: float
    uploaded_at: str


def upsert_stock(symbol: str, name: str, sector: str | None = None, industry: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stocks_master (symbol, name, sector, industry, added_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
              name=excluded.name,
              sector=COALESCE(excluded.sector, stocks_master.sector),
              industry=COALESCE(excluded.industry, stocks_master.industry)
            """,
            (symbol, name, sector, industry, now_iso()),
        )


def replace_holdings(holdings: Iterable[tuple[str, float, float]]) -> int:
    """Replace all holdings atomically. Each tuple = (symbol, quantity, avg_cost)."""
    ts = now_iso()
    with get_conn() as conn:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM portfolio_holdings")
        rows = [(s, q, c, ts) for (s, q, c) in holdings]
        conn.executemany(
            "INSERT INTO portfolio_holdings (symbol, quantity, avg_cost, uploaded_at) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.execute("COMMIT")
        return len(rows)


def list_holdings() -> list[Holding]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, symbol, quantity, avg_cost, uploaded_at FROM portfolio_holdings ORDER BY symbol"
        ).fetchall()
        return [Holding(**dict(r)) for r in rows]


def list_symbols() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT symbol FROM portfolio_holdings ORDER BY symbol").fetchall()
        return [r["symbol"] for r in rows]


def get_stock_meta(symbol: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT symbol, name, sector, industry FROM stocks_master WHERE symbol=?",
            (symbol,),
        ).fetchone()
        return dict(row) if row else None


def list_all_stock_meta() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol, name, sector, industry FROM stocks_master ORDER BY symbol"
        ).fetchall()
        return [dict(r) for r in rows]
