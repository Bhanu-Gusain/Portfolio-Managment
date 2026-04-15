"""Read/write daily action signals."""
from __future__ import annotations

from db.session import get_conn


def insert_signal(date: str, symbol: str, action: str, reason: str, score: float | None, trend_label: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO signals (date, symbol, action, reason, score, trend_label)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (date, symbol, action, reason, score, trend_label),
        )


def clear_signals_for_date(date: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM signals WHERE date=?", (date,))
        return cur.rowcount


def get_signals(date: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if date:
            rows = conn.execute(
                "SELECT * FROM signals WHERE date=? ORDER BY action, score DESC",
                (date,),
            ).fetchall()
        else:
            row = conn.execute("SELECT MAX(date) AS d FROM signals").fetchone()
            if not row or not row["d"]:
                return []
            rows = conn.execute(
                "SELECT * FROM signals WHERE date=? ORDER BY action, score DESC",
                (row["d"],),
            ).fetchall()
        return [dict(r) for r in rows]
