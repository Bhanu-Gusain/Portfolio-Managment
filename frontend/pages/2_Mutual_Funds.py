"""Mutual Funds page — Category + Sub-category donuts + per-scheme P&L."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.portfolio_data_loader import load as load_portfolio
from utils.config import get_settings

st.set_page_config(page_title="Mutual Funds · Portfolio", layout="wide")
st.title("💼 Mutual Funds")


def _fmt_inr(x, decimals: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    sign = "-" if x < 0 else ""
    return f"{sign}₹{abs(x):,.{decimals}f}"


def _fmt_pct(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:+.2f}%"


# ---------- pull enriched MF holdings direct from the workbook ----------

def _find_workbook() -> Path | None:
    base = get_settings().portfolio_data_dir
    for folder in (base, base / "raw", base / "templates"):
        if not folder.exists():
            continue
        for p in folder.iterdir():
            if p.suffix.lower() in (".xlsx", ".xls"):
                try:
                    xl = pd.ExcelFile(p, engine="openpyxl")
                    if {"MF Holdings", "Stocks Holdings"}.issubset(set(xl.sheet_names)):
                        return p
                except Exception:
                    continue
    return None


@st.cache_data(ttl=600, show_spinner=False)
def _read_mf_enriched(path_str: str) -> pd.DataFrame:
    path = Path(path_str)
    raw = pd.read_excel(path, sheet_name="MF Holdings", header=None)
    # Locate header row
    header_row = None
    for idx, row in raw.iterrows():
        cells = {str(v).strip() for v in row.tolist()}
        if {"Scheme Name", "Invested Value", "Current Value"}.issubset(cells):
            header_row = int(idx)
            break
    if header_row is None:
        return pd.DataFrame()
    df = pd.read_excel(path, sheet_name="MF Holdings", header=header_row)
    df = df.dropna(how="all").dropna(subset=["Scheme Name"]).reset_index(drop=True)
    return df


wb = _find_workbook()
if wb is None:
    st.info("No consolidated portfolio xlsx found. Drop your file in `portfolio_data/`.")
    st.stop()

mf = _read_mf_enriched(str(wb))
if mf.empty:
    st.info("`MF Holdings` sheet is empty or mis-formatted.")
    st.stop()

mf = mf.rename(columns={
    "Scheme Name": "scheme",
    "AMC": "amc",
    "Category": "category",
    "Sub-category": "sub_category",
    "Units": "units",
    "Invested Value": "invested",
    "Current Value": "current_value",
    "Returns": "unrealised_pnl",
    "XIRR": "xirr",
})
for c in ("units", "invested", "current_value", "unrealised_pnl"):
    mf[c] = pd.to_numeric(mf[c], errors="coerce")
mf["return_pct"] = (mf["unrealised_pnl"] / mf["invested"]) * 100


# ---------- summary ----------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Invested", _fmt_inr(mf["invested"].sum(), 0))
c2.metric("Current", _fmt_inr(mf["current_value"].sum(), 0))
c3.metric("Unrealised P&L", _fmt_inr(mf["unrealised_pnl"].sum(), 0),
          f"{mf['unrealised_pnl'].sum()/mf['invested'].sum()*100:+.2f}%" if mf['invested'].sum() else "")
c4.metric("Schemes", f"{mf['scheme'].nunique()}")

st.divider()


# ---------- allocation donuts ----------

DONUT_COLORS = ["#4F46E5", "#3B82F6", "#10B981", "#F59E0B", "#EF4444",
                "#A855F7", "#EC4899", "#14B8A6", "#F97316", "#84CC16"]


def _render(title: str, col: str) -> None:
    agg = (mf.groupby(col)
             .agg(current_value=("current_value", "sum"),
                  invested=("invested", "sum"),
                  unrealised_pnl=("unrealised_pnl", "sum"),
                  schemes=("scheme", "nunique"))
             .reset_index()
             .sort_values("current_value", ascending=False))
    total = agg["current_value"].sum()
    agg["alloc_pct"] = agg["current_value"] / total * 100 if total else 0
    agg["return_pct"] = (agg["unrealised_pnl"] / agg["invested"].replace(0, pd.NA)) * 100

    st.subheader(title)
    donut_col, table_col = st.columns([1, 2])

    with donut_col:
        fig = go.Figure(data=[go.Pie(
            labels=agg[col], values=agg["current_value"], hole=0.6,
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
            title: agg[col],
            "Schemes": agg["schemes"].astype(int),
            "Current (Allocation)": agg.apply(
                lambda r: f"{_fmt_inr(r['current_value'], 0)}  ·  {r['alloc_pct']:.2f}%", axis=1),
            "Returns (%)": agg.apply(
                lambda r: f"{_fmt_inr(r['unrealised_pnl'], 0)}  ({_fmt_pct(r['return_pct'])})", axis=1),
        })
        st.dataframe(table, use_container_width=True, hide_index=True,
                     height=min(320, 50 + 38 * len(table)))


_render("Category", "category")
st.divider()
_render("Sub-category", "sub_category")
st.divider()
_render("AMC", "amc")
st.divider()


# ---------- per-scheme P&L ----------

st.subheader("Per-scheme P&L")

pnl = pd.DataFrame({
    "Scheme": mf["scheme"],
    "AMC": mf["amc"],
    "Category": mf["category"],
    "Sub-category": mf["sub_category"],
    "Units": mf["units"].round(3),
    "Invested": mf["invested"].map(lambda v: _fmt_inr(v, 0)),
    "Current": mf["current_value"].map(lambda v: _fmt_inr(v, 0)),
    "Unrealised": mf["unrealised_pnl"].map(lambda v: _fmt_inr(v, 0)),
    "Return %": mf["return_pct"].map(_fmt_pct),
    "XIRR": mf["xirr"],
})
pnl = pnl.sort_values("Scheme").reset_index(drop=True)
st.dataframe(pnl, use_container_width=True, hide_index=True, height=400)
