"""Stocks page — Market cap + Sector + Nifty-index donuts + per-stock P&L."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services import metadata_enricher, price_fetcher
from services.fifo import compute_realised
from services.portfolio_data_loader import load as load_portfolio
from utils.config import PROJECT_ROOT, get_settings

st.set_page_config(page_title="Stocks · Portfolio", layout="wide")
st.title("📈 Stocks")


# ---------- helpers ----------

def _fmt_inr(x, decimals: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    sign = "-" if x < 0 else ""
    return f"{sign}₹{abs(x):,.{decimals}f}"


def _fmt_pct(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:+.2f}%"


def _load_override_map(path: Path, key: str, value: str) -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if key not in df.columns or value not in df.columns:
        return {}
    return {
        str(k).strip().upper().replace(".NS", ""): str(v).strip()
        for k, v in zip(df[key], df[value])
        if pd.notna(k) and pd.notna(v)
    }


@st.cache_data(ttl=3600, show_spinner=False)
def _enrich_cached(symbols: tuple[str, ...]) -> pd.DataFrame:
    return metadata_enricher.enrich(list(symbols))


@st.cache_data(ttl=3600, show_spinner="Fetching live prices…")
def _prices_cached(symbols: tuple[str, ...]):
    return price_fetcher.fetch_all(symbols, ())


@st.cache_data(ttl=600, show_spinner=False)
def _workbook_closing_prices() -> dict[str, float]:
    """Stock Name -> Closing price from the Groww xlsx (snapshot fallback)."""
    base = get_settings().portfolio_data_dir
    wb = None
    for folder in (base, base / "raw", base / "templates"):
        if not folder.exists():
            continue
        for p in folder.iterdir():
            if p.suffix.lower() in (".xlsx", ".xls"):
                try:
                    xl = pd.ExcelFile(p, engine="openpyxl")
                    if {"Stocks Holdings", "Stocks Transactions"}.issubset(set(xl.sheet_names)):
                        wb = p
                        break
                except Exception:
                    continue
        if wb:
            break
    if wb is None:
        return {}

    raw = pd.read_excel(wb, sheet_name="Stocks Holdings", header=None)
    header_row = None
    for idx, row in raw.iterrows():
        cells = {str(v).strip() for v in row.tolist()}
        if {"Stock Name", "Closing price"}.issubset(cells):
            header_row = int(idx); break
    if header_row is None:
        return {}

    df = pd.read_excel(wb, sheet_name="Stocks Holdings", header=header_row)
    df = df.dropna(subset=["Stock Name"])
    tx = pd.read_excel(wb, sheet_name="Stocks Transactions").dropna(subset=["Stock name", "Symbol"])
    name_to_symbol = {
        str(n).strip(): str(s).strip().upper()
        for n, s in zip(tx["Stock name"], tx["Symbol"])
    }
    out: dict[str, float] = {}
    for _, r in df.iterrows():
        sym = name_to_symbol.get(str(r["Stock Name"]).strip())
        price = pd.to_numeric(r.get("Closing price"), errors="coerce")
        if sym and pd.notna(price):
            out[sym] = float(price)
    return out


# ---------- load data ----------

data = load_portfolio()
holdings = data.stock_holdings.copy()
if holdings.empty:
    st.info("No stock holdings found. Add your xlsx to `portfolio_data/` and refresh.")
    st.stop()

holdings = holdings[holdings["symbol"].astype(str).str.strip() != ""].reset_index(drop=True)

# Live prices (best-effort; rows with no LTP keep avg_cost as LTP for allocation sizing)
prices = _prices_cached(tuple(holdings["symbol"]))
ltp_map = dict(zip(prices.stock_prices["symbol"].str.replace(".NS", "", regex=False).str.upper(),
                   prices.stock_prices["ltp"]))

holdings["symbol_clean"] = holdings["symbol"].str.upper().str.replace(".NS", "", regex=False)
holdings["ltp"] = holdings["symbol_clean"].map(ltp_map)

# Fallback: when LTP is missing, use Groww's snapshot Closing price from the xlsx.
snapshot = _workbook_closing_prices()
holdings["snapshot_price"] = holdings["symbol_clean"].map(snapshot)
holdings["effective_price"] = holdings["ltp"].fillna(holdings["snapshot_price"]).fillna(holdings["avg_cost"])

holdings["invested"] = holdings["quantity"] * holdings["avg_cost"]
holdings["current_value"] = holdings["quantity"] * holdings["effective_price"]
holdings["unrealised_pnl"] = holdings["current_value"] - holdings["invested"]
holdings["return_pct"] = (holdings["unrealised_pnl"] / holdings["invested"]) * 100

# Enrichment: sector + marketcap from yfinance (cached)
meta = _enrich_cached(tuple(holdings["symbol_clean"]))
sector_override = _load_override_map(PROJECT_ROOT / "data" / "sector_map.csv", "symbol", "sector")
mcap_override = _load_override_map(PROJECT_ROOT / "data" / "marketcap_map.csv", "symbol", "market_cap")

holdings = holdings.merge(meta[["symbol", "sector", "marketcap"]],
                          left_on="symbol_clean", right_on="symbol",
                          how="left", suffixes=("", "_meta"))

def _resolve_sector(row) -> str:
    s = sector_override.get(row["symbol_clean"]) or str(row.get("sector") or "").strip()
    return s or "Uncategorised"

_CAP_LABELS = {"large": "Large cap", "mid": "Mid cap", "small": "Small cap", "etf": "ETF"}

def _resolve_mcap(row) -> str:
    override = mcap_override.get(row["symbol_clean"])
    if override:
        return _CAP_LABELS.get(override.strip().lower(), override.strip())
    return metadata_enricher.market_cap_bucket(row.get("marketcap"))

holdings["sector_bucket"] = holdings.apply(_resolve_sector, axis=1)
holdings["mcap_bucket"] = holdings.apply(_resolve_mcap, axis=1)
holdings["index_bucket"] = holdings["symbol_clean"].apply(metadata_enricher.index_bucket)


# ---------- summary metrics ----------

total_invested = holdings["invested"].sum()
total_current = holdings["current_value"].sum()
total_unrealised = holdings["unrealised_pnl"].sum()
total_ret_pct = (total_unrealised / total_invested * 100) if total_invested else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Invested", _fmt_inr(total_invested, 0))
c2.metric("Current", _fmt_inr(total_current, 0))
c3.metric("Unrealised P&L", _fmt_inr(total_unrealised, 0), f"{total_ret_pct:+.2f}%")
c4.metric("Stocks", f"{len(holdings)}")

st.divider()


# ---------- allocation render helper ----------

DONUT_COLORS = ["#4F46E5", "#3B82F6", "#10B981", "#F59E0B", "#EF4444",
                "#A855F7", "#EC4899", "#14B8A6", "#F97316", "#84CC16"]


def _render_allocation(title: str, bucket_col: str) -> None:
    agg = (holdings.groupby(bucket_col)
                   .agg(current_value=("current_value", "sum"),
                        invested=("invested", "sum"),
                        unrealised_pnl=("unrealised_pnl", "sum"),
                        stocks=("symbol_clean", "nunique"))
                   .reset_index()
                   .sort_values("current_value", ascending=False))
    total = agg["current_value"].sum()
    agg["alloc_pct"] = agg["current_value"] / total * 100 if total else 0
    agg["return_pct"] = (agg["unrealised_pnl"] / agg["invested"].replace(0, pd.NA)) * 100

    st.subheader(title)
    donut_col, table_col = st.columns([1, 2])

    with donut_col:
        fig = go.Figure(data=[go.Pie(
            labels=agg[bucket_col],
            values=agg["current_value"],
            hole=0.6,
            marker=dict(colors=DONUT_COLORS[:len(agg)]),
            textinfo="percent",
            hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>",
        )])
        fig.update_layout(
            showlegend=False,
            margin=dict(t=10, b=10, l=10, r=10), height=280,
            annotations=[dict(text=title, x=0.5, y=0.5, font_size=13, showarrow=False)],
        )
        st.plotly_chart(fig, use_container_width=True)

    with table_col:
        table = pd.DataFrame({
            title: agg[bucket_col],
            "Stocks": agg["stocks"].astype(int),
            "Current (Allocation)": agg.apply(
                lambda r: f"{_fmt_inr(r['current_value'], 0)}  ·  {r['alloc_pct']:.2f}%", axis=1),
            "Returns (%)": agg.apply(
                lambda r: f"{_fmt_inr(r['unrealised_pnl'], 0)}  ({_fmt_pct(r['return_pct'])})", axis=1),
        })
        st.dataframe(table, use_container_width=True, hide_index=True, height=min(320, 50 + 38 * len(table)))


# ---------- stacked allocation sections ----------

_render_allocation("Market cap", "mcap_bucket")
st.divider()
_render_allocation("Sector allocation", "sector_bucket")
st.divider()
_render_allocation("Index membership", "index_bucket")
st.divider()


# ---------- per-stock P&L ----------

st.subheader("Per-stock P&L")

tx = data.stock_transactions.copy()
realised_per_symbol: dict[str, float] = {}
if not tx.empty:
    for sym, sub in tx.groupby(tx["symbol"].str.upper().str.replace(".NS", "", regex=False)):
        try:
            lots = compute_realised(
                sub, asset_col="symbol", qty_col="quantity", price_col="price",
                date_col="date", side_col="side", charges_col="charges",
            )
            realised_per_symbol[sym] = float(lots["gain"].sum()) if not lots.empty else 0.0
        except Exception:
            realised_per_symbol[sym] = 0.0

holdings["realised_pnl"] = holdings["symbol_clean"].map(realised_per_symbol).fillna(0.0)
holdings["total_pnl"] = holdings["unrealised_pnl"] + holdings["realised_pnl"]

pnl_table = holdings.assign(
    Symbol=holdings["symbol_clean"],
    Sector=holdings["sector_bucket"],
    **{
        "Market cap": holdings["mcap_bucket"],
        "Qty": holdings["quantity"].astype(float).round(2),
        "Avg cost": holdings["avg_cost"].map(lambda v: _fmt_inr(v, 2)),
        "LTP": holdings["effective_price"].map(lambda v: _fmt_inr(v, 2)),
        "Invested": holdings["invested"].map(lambda v: _fmt_inr(v, 0)),
        "Current": holdings["current_value"].map(lambda v: _fmt_inr(v, 0)),
        "Unrealised": holdings["unrealised_pnl"].map(lambda v: _fmt_inr(v, 0)),
        "Realised": holdings["realised_pnl"].map(lambda v: _fmt_inr(v, 0)),
        "Return %": holdings["return_pct"].map(_fmt_pct),
    },
)[["Symbol", "Sector", "Market cap", "Qty", "Avg cost", "LTP",
   "Invested", "Current", "Unrealised", "Realised", "Return %"]]

pnl_table = pnl_table.sort_values("Symbol").reset_index(drop=True)
st.dataframe(pnl_table, use_container_width=True, hide_index=True, height=500)

if prices.warnings:
    with st.expander("Price-fetch warnings"):
        for w in prices.warnings:
            st.write(w)
