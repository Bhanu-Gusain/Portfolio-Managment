"""Read/write portfolio snapshots."""
from __future__ import annotations

import json

from db.session import get_conn
from utils.time import now_iso


def insert_snapshot(
    total_value: float,
    total_pnl: float,
    portfolio_score: float,
    payload: dict,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO snapshots (taken_at, total_value, total_pnl, portfolio_score, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now_iso(), total_value, total_pnl, portfolio_score, json.dumps(payload)),
        )
        return int(cur.lastrowid)


def latest_snapshot() -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM snapshots ORDER BY taken_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        return d


def list_snapshots(limit: int = 30) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, taken_at, total_value, total_pnl, portfolio_score FROM snapshots ORDER BY taken_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
