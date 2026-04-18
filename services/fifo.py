"""FIFO realised-P&L computation from a transaction ledger.

Given a DataFrame of buys/sells (one symbol or ISIN at a time), walk through
chronologically, matching each sell to the oldest open lots. Emit realised
lots with buy_date, buy_price, sell_date, sell_price, qty, gain, charges_alloc.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

import pandas as pd


@dataclass
class RealisedLot:
    asset: str              # symbol or ISIN
    buy_date: str
    sell_date: str
    quantity: float
    buy_price: float
    sell_price: float
    gain: float
    charges_allocated: float

    def as_dict(self) -> dict:
        return {
            "asset": self.asset,
            "buy_date": self.buy_date,
            "sell_date": self.sell_date,
            "quantity": self.quantity,
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "gain": self.gain,
            "charges_allocated": self.charges_allocated,
        }


def compute_realised(
    transactions: pd.DataFrame,
    *,
    asset_col: str,
    qty_col: str,
    price_col: str,
    date_col: str = "date",
    side_col: str = "side",
    charges_col: str | None = "charges",
) -> pd.DataFrame:
    """Return one row per closed lot (or fragment) with realised gain.

    `transactions` can contain many assets mixed; FIFO is applied per-asset.
    """
    if transactions.empty:
        return pd.DataFrame(columns=[
            "asset", "buy_date", "sell_date", "quantity",
            "buy_price", "sell_price", "gain", "charges_allocated",
        ])

    df = transactions.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col, asset_col, qty_col, price_col, side_col])
    df = df.sort_values(date_col).reset_index(drop=True)

    realised: list[RealisedLot] = []
    for asset, group in df.groupby(asset_col):
        open_lots: deque[dict] = deque()
        for _, row in group.iterrows():
            side = str(row[side_col]).lower()
            qty = float(row[qty_col])
            price = float(row[price_col])
            d = row[date_col].strftime("%Y-%m-%d")
            charges = float(row[charges_col]) if charges_col and charges_col in row and pd.notna(row[charges_col]) else 0.0

            if side == "buy":
                open_lots.append({"qty": qty, "price": price, "date": d, "charges": charges})
                continue

            if side != "sell":
                continue

            remaining = qty
            while remaining > 1e-9 and open_lots:
                lot = open_lots[0]
                match_qty = min(lot["qty"], remaining)
                gain = (price - lot["price"]) * match_qty
                alloc_charges = charges * (match_qty / qty) if qty else 0.0
                realised.append(RealisedLot(
                    asset=asset,
                    buy_date=lot["date"],
                    sell_date=d,
                    quantity=match_qty,
                    buy_price=lot["price"],
                    sell_price=price,
                    gain=gain - alloc_charges,
                    charges_allocated=alloc_charges,
                ))
                lot["qty"] -= match_qty
                remaining -= match_qty
                if lot["qty"] <= 1e-9:
                    open_lots.popleft()

            # If `remaining` > 0 at this point, the ledger has a short sell; we ignore it.

    if not realised:
        return pd.DataFrame(columns=[
            "asset", "buy_date", "sell_date", "quantity",
            "buy_price", "sell_price", "gain", "charges_allocated",
        ])
    return pd.DataFrame([r.as_dict() for r in realised])


def fy_label(d: pd.Timestamp | str) -> str:
    """Indian financial year label: Apr 2024 → 'FY24-25', Feb 2025 → 'FY24-25'."""
    ts = pd.to_datetime(d)
    y = ts.year
    if ts.month >= 4:
        start = y
    else:
        start = y - 1
    return f"FY{str(start)[-2:]}-{str(start + 1)[-2:]}"
