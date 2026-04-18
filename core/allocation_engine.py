"""Allocation summary: sector / market-cap / MF-category breakdowns from positions."""
from __future__ import annotations

import pandas as pd


def by_asset_type(positions: pd.DataFrame) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(columns=["asset_type", "value", "weight_pct"])
    agg = (
        positions.groupby("asset_type")["current_value"]
        .sum(min_count=1)
        .reset_index()
        .rename(columns={"current_value": "value"})
    )
    total = agg["value"].sum()
    agg["weight_pct"] = agg["value"] / total * 100.0 if total else 0.0
    return agg


def by_sector(positions: pd.DataFrame, sector_map: dict[str, str]) -> pd.DataFrame:
    stock_rows = positions[positions["asset_type"] == "stock"].copy()
    if stock_rows.empty:
        return pd.DataFrame(columns=["sector", "value", "weight_pct"])
    stock_rows["sector"] = stock_rows["identifier"].map(sector_map).fillna("Unknown")
    agg = stock_rows.groupby("sector")["current_value"].sum(min_count=1).reset_index()
    agg = agg.rename(columns={"current_value": "value"})
    total = agg["value"].sum()
    agg["weight_pct"] = agg["value"] / total * 100.0 if total else 0.0
    return agg.sort_values("value", ascending=False).reset_index(drop=True)


def by_market_cap(positions: pd.DataFrame, cap_map: dict[str, str]) -> pd.DataFrame:
    stock_rows = positions[positions["asset_type"] == "stock"].copy()
    if stock_rows.empty:
        return pd.DataFrame(columns=["market_cap", "value", "weight_pct"])
    stock_rows["market_cap"] = stock_rows["identifier"].map(cap_map).fillna("Unknown")
    agg = stock_rows.groupby("market_cap")["current_value"].sum(min_count=1).reset_index()
    agg = agg.rename(columns={"current_value": "value"})
    total = agg["value"].sum()
    agg["weight_pct"] = agg["value"] / total * 100.0 if total else 0.0
    return agg.sort_values("value", ascending=False).reset_index(drop=True)


def by_mf_category(positions: pd.DataFrame, mf_prices: pd.DataFrame) -> pd.DataFrame:
    mf_rows = positions[positions["asset_type"] == "mutual_fund"].copy()
    if mf_rows.empty or mf_prices.empty:
        return pd.DataFrame(columns=["category", "value", "weight_pct"])
    cat_map = mf_prices.set_index("isin")["category"].to_dict()
    mf_rows["category"] = mf_rows["identifier"].map(cat_map).fillna("Unknown")
    agg = mf_rows.groupby("category")["current_value"].sum(min_count=1).reset_index()
    agg = agg.rename(columns={"current_value": "value"})
    total = agg["value"].sum()
    agg["weight_pct"] = agg["value"] / total * 100.0 if total else 0.0
    return agg.sort_values("value", ascending=False).reset_index(drop=True)
