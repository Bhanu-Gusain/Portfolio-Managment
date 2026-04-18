"""Portfolio positions + summary computed from in-memory DataFrames.

Combines stock_holdings + mf_holdings with a price frame (stock_prices +
mf_prices) to produce a unified positions DataFrame. No DB, no side effects.
"""
from __future__ import annotations

import pandas as pd


POSITION_COLUMNS = [
    "asset_type", "identifier", "name", "quantity", "avg_cost", "ltp",
    "invested", "current_value", "pnl", "pnl_pct", "weight_pct",
    "day_change_pct",
]


def build_positions(
    stock_holdings: pd.DataFrame,
    mf_holdings: pd.DataFrame,
    stock_prices: pd.DataFrame,
    mf_prices: pd.DataFrame,
) -> pd.DataFrame:
    """Return a unified positions DataFrame. LTP is NaN when price missing."""
    rows: list[dict] = []

    stock_price_map = (
        stock_prices.set_index("symbol").to_dict("index") if not stock_prices.empty else {}
    )
    if not stock_holdings.empty:
        for _, h in stock_holdings.iterrows():
            sym = str(h["symbol"]).strip().upper()
            qty = float(h["quantity"]) if pd.notna(h["quantity"]) else 0.0
            avg = float(h["avg_cost"]) if pd.notna(h["avg_cost"]) else 0.0
            pm = stock_price_map.get(sym, {})
            ltp = pm.get("ltp")
            day_chg = pm.get("day_change_pct")
            invested = qty * avg
            current = qty * ltp if ltp is not None else None
            pnl = current - invested if current is not None else None
            pnl_pct = (pnl / invested * 100.0) if (pnl is not None and invested > 0) else None
            rows.append({
                "asset_type": "stock",
                "identifier": sym,
                "name": sym,
                "quantity": qty,
                "avg_cost": avg,
                "ltp": ltp,
                "invested": invested,
                "current_value": current,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "weight_pct": None,
                "day_change_pct": day_chg,
            })

    mf_price_map = (
        mf_prices.set_index("isin").to_dict("index") if not mf_prices.empty else {}
    )
    if not mf_holdings.empty:
        for _, h in mf_holdings.iterrows():
            isin = str(h["isin"]).strip().upper()
            units = float(h["units"]) if pd.notna(h["units"]) else 0.0
            avg = float(h["avg_nav"]) if pd.notna(h["avg_nav"]) else 0.0
            name = str(h["scheme_name"]).strip() or isin
            pm = mf_price_map.get(isin, {})
            nav = pm.get("nav")
            invested = units * avg
            current = units * nav if nav is not None else None
            pnl = current - invested if current is not None else None
            pnl_pct = (pnl / invested * 100.0) if (pnl is not None and invested > 0) else None
            rows.append({
                "asset_type": "mutual_fund",
                "identifier": isin,
                "name": name,
                "quantity": units,
                "avg_cost": avg,
                "ltp": nav,
                "invested": invested,
                "current_value": current,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "weight_pct": None,
                "day_change_pct": None,
            })

    if not rows:
        return pd.DataFrame(columns=POSITION_COLUMNS)

    df = pd.DataFrame(rows)
    total_value = df["current_value"].dropna().sum()
    if total_value > 0:
        df["weight_pct"] = df["current_value"].apply(
            lambda v: (v / total_value * 100.0) if pd.notna(v) else None
        )
    return df[POSITION_COLUMNS].sort_values(
        "current_value", ascending=False, na_position="last"
    ).reset_index(drop=True)


def summarise(positions: pd.DataFrame, realised_ytd: float = 0.0) -> dict:
    """Top-line KPIs for the Overview tab."""
    if positions.empty:
        return {
            "total_value": 0.0, "total_invested": 0.0, "unrealised_pnl": 0.0,
            "unrealised_pnl_pct": 0.0, "realised_ytd": realised_ytd,
            "day_change": 0.0, "num_positions": 0,
        }
    total_value = float(positions["current_value"].dropna().sum())
    total_invested = float(positions["invested"].sum())
    unrealised = total_value - total_invested if total_value else 0.0
    pct = (unrealised / total_invested * 100.0) if total_invested > 0 else 0.0

    prev_value = 0.0
    for _, r in positions.iterrows():
        ltp = r.get("ltp")
        dc = r.get("day_change_pct")
        qty = r.get("quantity") or 0
        if ltp is None or dc is None:
            continue
        prev = ltp / (1 + dc / 100.0) if (1 + dc / 100.0) != 0 else ltp
        prev_value += qty * prev
    day_change = total_value - prev_value if prev_value else 0.0

    return {
        "total_value": total_value,
        "total_invested": total_invested,
        "unrealised_pnl": unrealised,
        "unrealised_pnl_pct": pct,
        "realised_ytd": realised_ytd,
        "day_change": day_change,
        "num_positions": len(positions),
    }
