"""Read/write OHLCV prices and technical indicators."""
from __future__ import annotations

import pandas as pd

from db.session import get_conn


def upsert_prices(symbol: str, df: pd.DataFrame) -> int:
    """df must have columns: date (str ISO), open, high, low, close, volume."""
    if df.empty:
        return 0
    rows = [
        (symbol, str(r["date"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), int(r["volume"]))
        for _, r in df.iterrows()
    ]
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO price_data (symbol, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
              open=excluded.open, high=excluded.high, low=excluded.low,
              close=excluded.close, volume=excluded.volume
            """,
            rows,
        )
    return len(rows)


def load_prices(symbol: str) -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM price_data WHERE symbol=? ORDER BY date",
            conn,
            params=(symbol,),
        )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    return df


def latest_price(symbol: str) -> float | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT close FROM price_data WHERE symbol=? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return float(row["close"]) if row else None


def latest_price_date(symbol: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT date FROM price_data WHERE symbol=? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return row["date"] if row else None


def upsert_indicators(symbol: str, date: str, indicators: dict) -> None:
    cols = [
        "ema21", "ema50", "ema200", "rsi14", "macd", "macd_signal", "macd_hist",
        "high_52w", "low_52w", "trend_label", "is_breakout",
    ]
    values = [symbol, date] + [indicators.get(c) for c in cols]
    placeholders = ",".join(["?"] * (len(cols) + 2))
    set_clause = ", ".join([f"{c}=excluded.{c}" for c in cols])
    with get_conn() as conn:
        conn.execute(
            f"""
            INSERT INTO technical_indicators (symbol, date, {",".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(symbol, date) DO UPDATE SET {set_clause}
            """,
            values,
        )


def latest_indicators(symbol: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM technical_indicators
            WHERE symbol=? ORDER BY date DESC LIMIT 1
            """,
            (symbol,),
        ).fetchone()
        return dict(row) if row else None


def upsert_fundamentals(symbol: str, data: dict, source: str, updated_at: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO fundamentals (symbol, roe, sales_growth_3y, debt_to_equity, pe, market_cap, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
              roe=excluded.roe, sales_growth_3y=excluded.sales_growth_3y,
              debt_to_equity=excluded.debt_to_equity, pe=excluded.pe,
              market_cap=excluded.market_cap, source=excluded.source,
              updated_at=excluded.updated_at
            """,
            (
                symbol,
                data.get("roe"),
                data.get("sales_growth_3y"),
                data.get("debt_to_equity"),
                data.get("pe"),
                data.get("market_cap"),
                source,
                updated_at,
            ),
        )


def get_fundamentals(symbol: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM fundamentals WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row else None
