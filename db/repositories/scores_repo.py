"""Read/write scoring results."""
from __future__ import annotations

import json

from db.session import get_conn


def upsert_score(symbol: str, date: str, score: float, label: str, breakdown: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO scores (symbol, date, score, label, factor_breakdown)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
              score=excluded.score, label=excluded.label, factor_breakdown=excluded.factor_breakdown
            """,
            (symbol, date, score, label, json.dumps(breakdown)),
        )


def get_score(symbol: str, date: str | None = None) -> dict | None:
    with get_conn() as conn:
        if date:
            row = conn.execute(
                "SELECT * FROM scores WHERE symbol=? AND date=?", (symbol, date)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM scores WHERE symbol=? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["factor_breakdown"] = json.loads(result["factor_breakdown"])
        return result


def latest_scores() -> list[dict]:
    """Latest score per symbol."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.symbol, s.date, s.score, s.label, s.factor_breakdown
            FROM scores s
            INNER JOIN (
              SELECT symbol, MAX(date) AS max_date FROM scores GROUP BY symbol
            ) x ON s.symbol = x.symbol AND s.date = x.max_date
            ORDER BY s.score DESC
            """
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["factor_breakdown"] = json.loads(d["factor_breakdown"])
        out.append(d)
    return out
