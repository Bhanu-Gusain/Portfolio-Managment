"""Portfolio dashboard — file-driven, in-memory, no DB, no LLM.

Reads the user's CSV/XLSX files from `portfolio_data/`, fetches live prices
(yfinance for stocks, AMFI for mutual funds), and renders 7 data-visualisation
tabs. Every computation is in-memory per Streamlit session.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date, datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import allocation_engine, performance_engine, portfolio_engine, risk_engine
from services import fifo, price_fetcher
from services.portfolio_data_loader import PortfolioData, load as load_portfolio
from utils.config import PROJECT_ROOT, get_settings

st.set_page_config(
    page_title="Portfolio Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------- small helpers ----------

def _fmt_inr(x: float | None, decimals: int = 0) -> str:
    if x is None or pd.isna(x):
        return "—"
    fmt = f"{{:,.{decimals}f}}"
    return f"₹{fmt.format(x)}"


def _fmt_pct(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:+.2f}%"


def _load_csv_map(path: Path, key: str, value: str) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}
    if key not in df.columns or value not in df.columns:
        return {}
    return {
        str(k).strip().upper(): str(v).strip()
        for k, v in zip(df[key], df[value])
        if pd.notna(k) and pd.notna(v)
    }


# ---------- cached loaders ----------

@st.cache_data(ttl=600, show_spinner=False)
def _load_data_cached(_nonce: int) -> PortfolioData:
    return load_portfolio()


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_prices_cached(stock_symbols: tuple[str, ...], mf_isins: tuple[str, ...], _nonce: int):
    return price_fetcher.fetch_all(stock_symbols, mf_isins)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_mf_history_cached(scheme_codes: tuple[str, ...], _nonce: int):
    return price_fetcher.fetch_mf_history(scheme_codes)


if "reload_nonce" not in st.session_state:
    st.session_state["reload_nonce"] = 0


# ---------- sidebar ----------

with st.sidebar:
    st.title("📁 Portfolio Data")
    settings = get_settings()
    st.caption(f"Reading from `{settings.portfolio_data_dir.relative_to(PROJECT_ROOT)}/`")

    if st.button("🔁 Reload files", use_container_width=True):
        st.session_state["reload_nonce"] += 1
        st.cache_data.clear()

    if st.button("🔄 Refresh prices", use_container_width=True):
        deleted = price_fetcher.clear_today_cache()
        st.session_state["reload_nonce"] += 1
        st.cache_data.clear()
        st.success(f"Cleared {deleted} cache file(s). Prices will refetch.")

    data = _load_data_cached(st.session_state["reload_nonce"])

    st.markdown("### Loaded files")
    status = data.status()
    label_map = {
        "stock_holdings": "Stock holdings",
        "mf_holdings": "Mutual fund holdings",
        "stock_transactions": "Stock transactions",
        "mf_transactions": "Mutual fund transactions",
        "dividends": "Dividends",
        "watchlist": "Watchlist",
    }
    for key, s in status.items():
        icon = "✅" if s["rows"] > 0 else "—"
        st.markdown(f"{icon} **{label_map[key]}** · {s['rows']} rows")

    if data.warnings:
        with st.expander(f"⚠️  {len(data.warnings)} warnings"):
            for w in data.warnings:
                st.markdown(f"- {w}")

    st.markdown("---")
    st.caption("Drop new files into the folder above, then click **Reload files**.")


# ---------- no data → quickstart ----------

if data.is_empty():
    st.title("Portfolio Dashboard")
    st.info(
        "No portfolio data loaded yet.\n\n"
        f"1. Run `python scripts/init_portfolio_data.py` to create "
        f"`{settings.portfolio_data_dir.name}/` with empty CSV templates.\n"
        "2. Fill in `stock_holdings.csv` and/or `mf_holdings.csv` with your holdings.\n"
        "3. Optionally add transactions, dividends, watchlist.\n"
        "4. Click **Reload files** in the sidebar."
    )
    st.stop()


# ---------- fetch prices ----------

stock_symbols = tuple(sorted(data.stock_holdings["symbol"].dropna().astype(str).str.upper().tolist()))
mf_isins = tuple(sorted(data.mf_holdings["isin"].dropna().astype(str).str.upper().tolist()))

# Include watchlist tickers so tab 7 has prices
if not data.watchlist.empty:
    extra_syms = [
        s.strip().upper() for s, t in zip(data.watchlist["symbol_or_isin"], data.watchlist["asset_type"])
        if str(t).lower() == "stock"
    ]
    extra_isins = [
        s.strip().upper() for s, t in zip(data.watchlist["symbol_or_isin"], data.watchlist["asset_type"])
        if str(t).lower() == "mutual_fund"
    ]
    stock_symbols = tuple(sorted(set(stock_symbols) | set(extra_syms)))
    mf_isins = tuple(sorted(set(mf_isins) | set(extra_isins)))

with st.spinner("Fetching live prices (yfinance + AMFI)..."):
    prices = _fetch_prices_cached(stock_symbols, mf_isins, st.session_state["reload_nonce"])

if prices.warnings:
    with st.sidebar:
        with st.expander(f"ℹ️  {len(prices.warnings)} price warnings"):
            for w in prices.warnings:
                st.markdown(f"- {w}")


# ---------- derive positions ----------

positions = portfolio_engine.build_positions(
    data.stock_holdings, data.mf_holdings, prices.stock_prices, prices.mf_prices,
)

# Realised P&L (FIFO) — YTD for current calendar year + full history
realised_stocks = fifo.compute_realised(
    data.stock_transactions, asset_col="symbol",
    qty_col="quantity", price_col="price",
) if not data.stock_transactions.empty else pd.DataFrame()
realised_mf = fifo.compute_realised(
    data.mf_transactions, asset_col="isin",
    qty_col="units", price_col="nav",
) if not data.mf_transactions.empty else pd.DataFrame()

realised_all = pd.concat([df for df in (realised_stocks, realised_mf) if not df.empty], ignore_index=True) \
    if any(not df.empty for df in (realised_stocks, realised_mf)) else pd.DataFrame()

realised_ytd = 0.0
if not realised_all.empty:
    realised_all["sell_date"] = pd.to_datetime(realised_all["sell_date"])
    realised_all["fy"] = realised_all["sell_date"].apply(fifo.fy_label)
    this_fy = fifo.fy_label(pd.Timestamp(date.today()))
    realised_ytd = float(realised_all.loc[realised_all["fy"] == this_fy, "gain"].sum())

summary = portfolio_engine.summarise(positions, realised_ytd=realised_ytd)

sector_map = _load_csv_map(PROJECT_ROOT / "data" / "sector_map.csv", "symbol", "sector")
cap_map = _load_csv_map(PROJECT_ROOT / "data" / "marketcap_map.csv", "symbol", "market_cap")


# ---------- header ----------

st.title("Portfolio Dashboard")
st.caption(
    f"Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
    f"{len(stock_symbols)} stock symbols · {len(mf_isins)} MF ISINs · "
    f"{'AMFI category metadata cached' if not prices.mf_prices.empty else 'AMFI unavailable'}"
)

tab_overview, tab_holdings, tab_txns, tab_perf, tab_risk, tab_divs, tab_watch = st.tabs([
    "Overview", "Holdings", "Transactions", "Performance",
    "Allocation & Risk", "Dividends", "Watchlist",
])


# ================== Tab 1: Overview ==================

with tab_overview:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Value", _fmt_inr(summary["total_value"]))
    c2.metric("Invested", _fmt_inr(summary["total_invested"]))
    c3.metric(
        "Unrealised P&L",
        _fmt_inr(summary["unrealised_pnl"]),
        _fmt_pct(summary["unrealised_pnl_pct"]),
    )
    c4.metric("Realised (this FY)", _fmt_inr(summary["realised_ytd"]))
    c5.metric("Today's Change", _fmt_inr(summary["day_change"]))

    left, right = st.columns([1, 1])

    with left:
        asset_mix = allocation_engine.by_asset_type(positions)
        if not asset_mix.empty and asset_mix["value"].sum() > 0:
            fig = px.pie(
                asset_mix, names="asset_type", values="value",
                title="Asset class split", hole=0.45,
            )
            fig.update_traces(textinfo="label+percent")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No current values yet (price fetch may be offline).")

    with right:
        if "day_change_pct" in positions.columns and positions["day_change_pct"].notna().any():
            pos_today = positions[positions["day_change_pct"].notna()].copy()
            pos_today["abs_change_inr"] = pos_today["quantity"] * pos_today["ltp"] - (
                pos_today["quantity"] * pos_today["ltp"] / (1 + pos_today["day_change_pct"] / 100.0)
            )
            top = pd.concat([
                pos_today.nlargest(5, "day_change_pct"),
                pos_today.nsmallest(5, "day_change_pct"),
            ]).drop_duplicates(subset=["identifier"])
            fig = px.bar(
                top, x="day_change_pct", y="name", orientation="h",
                color="day_change_pct", color_continuous_scale=["#c0392b", "#ecf0f1", "#27ae60"],
                title="Top movers today (%)",
                color_continuous_midpoint=0,
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Day movers: price data unavailable.")

    if not data.stock_transactions.empty or not data.mf_transactions.empty:
        hist_map = prices.stock_history
        mf_history_frames: dict[str, pd.DataFrame] = {}
        mf_isin_to_code: dict[str, str] = {}
        if not prices.mf_prices.empty:
            mf_isin_to_code = dict(zip(prices.mf_prices["isin"], prices.mf_prices["scheme_code"]))
            codes = tuple(sorted({c for c in mf_isin_to_code.values() if c}))
            mf_hist, mf_warn = _fetch_mf_history_cached(codes, st.session_state["reload_nonce"])
            mf_history_frames = mf_hist
            if mf_warn:
                with st.sidebar:
                    with st.expander("ℹ️  mfapi.in warnings"):
                        for w in mf_warn:
                            st.markdown(f"- {w}")

        ts = performance_engine.portfolio_value_timeseries(
            data.stock_transactions, data.mf_transactions,
            hist_map, mf_history_frames, mf_isin_to_code,
        )
        if not ts.empty:
            st.markdown("### Portfolio value (reconstructed)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ts["date"], y=ts["value"], mode="lines", name="Value", line={"color": "#2e86de"}))
            fig.add_trace(go.Scatter(x=ts["date"], y=ts["invested"], mode="lines", name="Invested", line={"color": "#95a5a6", "dash": "dot"}))
            fig.update_layout(height=320, margin=dict(t=30, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)


# ================== Tab 2: Holdings ==================

with tab_holdings:
    if positions.empty:
        st.info("Add `stock_holdings.csv` and/or `mf_holdings.csv` to `portfolio_data/`.")
    else:
        type_filter = st.radio(
            "Filter", ["All", "Stocks only", "Mutual funds only"],
            horizontal=True, label_visibility="collapsed",
        )
        view = positions.copy()
        if type_filter == "Stocks only":
            view = view[view["asset_type"] == "stock"]
        elif type_filter == "Mutual funds only":
            view = view[view["asset_type"] == "mutual_fund"]

        st.dataframe(
            view[[
                "asset_type", "identifier", "name", "quantity", "avg_cost",
                "ltp", "invested", "current_value", "pnl", "pnl_pct", "weight_pct",
            ]],
            use_container_width=True, hide_index=True,
            column_config={
                "asset_type": "Type",
                "identifier": "Symbol/ISIN",
                "name": "Name",
                "quantity": st.column_config.NumberColumn("Qty", format="%.4f"),
                "avg_cost": st.column_config.NumberColumn("Avg Cost", format="₹%.2f"),
                "ltp": st.column_config.NumberColumn("LTP", format="₹%.2f"),
                "invested": st.column_config.NumberColumn("Invested", format="₹%.0f"),
                "current_value": st.column_config.NumberColumn("Current", format="₹%.0f"),
                "pnl": st.column_config.NumberColumn("P&L", format="₹%.0f"),
                "pnl_pct": st.column_config.NumberColumn("P&L %", format="%.2f%%"),
                "weight_pct": st.column_config.NumberColumn("Weight %", format="%.2f%%"),
            },
        )

        if st.toggle("Show as treemap"):
            tree = view.dropna(subset=["current_value"]).copy()
            if not tree.empty:
                fig = px.treemap(
                    tree, path=["asset_type", "name"],
                    values="current_value", color="pnl_pct",
                    color_continuous_scale=["#c0392b", "#ecf0f1", "#27ae60"],
                    color_continuous_midpoint=0,
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No current values to plot.")


# ================== Tab 3: Transactions ==================

with tab_txns:
    if data.stock_transactions.empty and data.mf_transactions.empty:
        st.info("📄 This tab needs `stock_transactions.csv` or `mf_transactions.csv`.")
    else:
        combined = pd.concat([
            data.stock_transactions.assign(asset_type="stock", identifier=data.stock_transactions.get("symbol"),
                                           qty=data.stock_transactions.get("quantity"),
                                           unit_price=data.stock_transactions.get("price")),
            data.mf_transactions.assign(asset_type="mutual_fund", identifier=data.mf_transactions.get("isin"),
                                        qty=data.mf_transactions.get("units"),
                                        unit_price=data.mf_transactions.get("nav")),
        ], ignore_index=True) if (not data.stock_transactions.empty and not data.mf_transactions.empty) else (
            data.stock_transactions.assign(asset_type="stock", identifier=data.stock_transactions.get("symbol"),
                                           qty=data.stock_transactions.get("quantity"),
                                           unit_price=data.stock_transactions.get("price"))
            if not data.stock_transactions.empty else
            data.mf_transactions.assign(asset_type="mutual_fund", identifier=data.mf_transactions.get("isin"),
                                        qty=data.mf_transactions.get("units"),
                                        unit_price=data.mf_transactions.get("nav"))
        )
        combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
        combined = combined.dropna(subset=["date"]).sort_values("date", ascending=False)

        c1, c2, c3 = st.columns(3)
        types = c1.multiselect("Type", ["stock", "mutual_fund"], default=["stock", "mutual_fund"])
        sides = c2.multiselect("Side", ["buy", "sell"], default=["buy", "sell"])
        assets = c3.multiselect(
            "Asset", sorted(combined["identifier"].dropna().unique().tolist()),
        )
        filt = combined[combined["asset_type"].isin(types) & combined["side"].isin(sides)]
        if assets:
            filt = filt[filt["identifier"].isin(assets)]

        st.dataframe(
            filt[["date", "asset_type", "identifier", "side", "qty", "unit_price"]].rename(
                columns={"unit_price": "price/nav"}
            ),
            use_container_width=True, hide_index=True,
        )

        st.markdown("### Monthly buy/sell")
        m = filt.copy()
        m["month"] = m["date"].dt.to_period("M").astype(str)
        m["amount"] = m["qty"] * m["unit_price"]
        agg = m.groupby(["month", "side"])["amount"].sum().reset_index()
        if not agg.empty:
            fig = px.bar(
                agg, x="month", y="amount", color="side", barmode="group",
                color_discrete_map={"buy": "#3498db", "sell": "#e67e22"},
            )
            fig.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Realised P&L (FIFO)")
        if realised_all.empty:
            st.caption("No closed lots yet.")
        else:
            fy_agg = (
                realised_all.groupby("fy")
                .agg(gain=("gain", "sum"), charges=("charges_allocated", "sum"), lots=("gain", "count"))
                .reset_index()
            )
            st.dataframe(fy_agg, hide_index=True, use_container_width=True,
                         column_config={
                             "gain": st.column_config.NumberColumn("Realised ₹", format="₹%.0f"),
                             "charges": st.column_config.NumberColumn("Charges ₹", format="₹%.2f"),
                         })
            with st.expander("Lot-level detail"):
                st.dataframe(realised_all, hide_index=True, use_container_width=True)


# ================== Tab 4: Performance ==================

with tab_perf:
    if data.stock_transactions.empty and data.mf_transactions.empty:
        st.info("📄 This tab needs transaction history (`stock_transactions.csv` or `mf_transactions.csv`).")
    else:
        hist_map = prices.stock_history
        mf_isin_to_code = (
            dict(zip(prices.mf_prices["isin"], prices.mf_prices["scheme_code"]))
            if not prices.mf_prices.empty else {}
        )
        codes = tuple(sorted({c for c in mf_isin_to_code.values() if c}))
        mf_history_frames, mf_hist_warn = _fetch_mf_history_cached(codes, st.session_state["reload_nonce"])

        ts = performance_engine.portfolio_value_timeseries(
            data.stock_transactions, data.mf_transactions,
            hist_map, mf_history_frames, mf_isin_to_code,
        )
        if ts.empty:
            st.warning("Could not reconstruct timeseries — missing historical prices.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ts["date"], y=ts["value"], mode="lines", name="Portfolio"))
            fig.add_trace(go.Scatter(x=ts["date"], y=ts["invested"], mode="lines", name="Invested",
                                     line={"dash": "dot", "color": "#95a5a6"}))
            if not prices.benchmark_history.empty:
                bench = prices.benchmark_history.copy()
                # Scale benchmark to portfolio's first value
                first_val = ts.iloc[0]["value"] if ts.iloc[0]["value"] > 0 else ts[ts["value"] > 0]["value"].iloc[0] if (ts["value"] > 0).any() else 100000.0
                bench = bench[bench["date"] >= ts.iloc[0]["date"]]
                if not bench.empty and bench["close"].iloc[0] > 0:
                    scale = first_val / bench["close"].iloc[0]
                    bench["scaled"] = bench["close"] * scale
                    fig.add_trace(go.Scatter(x=bench["date"], y=bench["scaled"], mode="lines",
                                             name="NIFTY 50 (scaled)", line={"color": "#e67e22"}))
            fig.update_layout(height=420, margin=dict(t=20, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)

        # XIRR per bucket
        st.markdown("### XIRR")
        xirr_rows: list[dict] = []

        def _xirr_from_txns(txns: pd.DataFrame, qty_col: str, price_col: str, label: str, current_value: float) -> None:
            if txns.empty:
                return
            cfs: list[tuple[str, float]] = []
            for _, r in txns.iterrows():
                try:
                    q = float(r[qty_col]); p = float(r[price_col])
                except (TypeError, ValueError):
                    continue
                side = str(r.get("side", "")).lower()
                sign = -1 if side == "buy" else 1 if side == "sell" else 0
                if sign == 0:
                    continue
                cfs.append((r["date"], sign * q * p))
            cfs.append((date.today().isoformat(), current_value))
            rate = performance_engine.xirr(cfs)
            xirr_rows.append({"bucket": label, "xirr": rate})

        stock_current = float(positions.loc[positions["asset_type"] == "stock", "current_value"].dropna().sum())
        mf_current = float(positions.loc[positions["asset_type"] == "mutual_fund", "current_value"].dropna().sum())
        _xirr_from_txns(data.stock_transactions, "quantity", "price", "Stocks only", stock_current)
        _xirr_from_txns(data.mf_transactions, "units", "nav", "Mutual funds only", mf_current)

        combined_txns = pd.concat([
            data.stock_transactions.rename(columns={"quantity": "q", "price": "p"}).assign(q=lambda d: d["q"], p=lambda d: d["p"]),
            data.mf_transactions.rename(columns={"units": "q", "nav": "p"}),
        ], ignore_index=True) if (not data.stock_transactions.empty and not data.mf_transactions.empty) else None
        if combined_txns is not None:
            _xirr_from_txns(combined_txns, "q", "p", "Whole portfolio", stock_current + mf_current)

        if xirr_rows:
            xdf = pd.DataFrame(xirr_rows)
            xdf["xirr_pct"] = xdf["xirr"].apply(lambda r: f"{r * 100:.2f}%" if r is not None else "—")
            st.dataframe(xdf[["bucket", "xirr_pct"]], hide_index=True, use_container_width=True)


# ================== Tab 5: Allocation & Risk ==================

with tab_risk:
    if positions.empty:
        st.info("Add holdings to see allocation and risk.")
    else:
        r1c1, r1c2, r1c3 = st.columns(3)
        with r1c1:
            sec = allocation_engine.by_sector(positions, sector_map)
            if not sec.empty and sec["value"].sum() > 0:
                st.plotly_chart(px.pie(sec, names="sector", values="value", title="Sector (stocks)"),
                                use_container_width=True)
            else:
                st.caption("No sector data (add to `data/sector_map.csv`).")
        with r1c2:
            cap = allocation_engine.by_market_cap(positions, cap_map)
            if not cap.empty and cap["value"].sum() > 0:
                st.plotly_chart(px.pie(cap, names="market_cap", values="value", title="Market cap (stocks)"),
                                use_container_width=True)
            else:
                st.caption("No market-cap data (add to `data/marketcap_map.csv`).")
        with r1c3:
            mfc = allocation_engine.by_mf_category(positions, prices.mf_prices)
            if not mfc.empty and mfc["value"].sum() > 0:
                st.plotly_chart(px.pie(mfc, names="category", values="value", title="MF category"),
                                use_container_width=True)
            else:
                st.caption("No MF category data (AMFI feed unavailable or no MFs).")

        st.markdown("### Risk warnings")
        warnings = risk_engine.evaluate(positions, sector_map=sector_map)
        if not warnings:
            st.success("No risk warnings — portfolio within configured limits.")
        else:
            sev_icon = {"high": "🔴", "med": "🟡", "low": "🔵"}
            for w in warnings:
                with st.container(border=True):
                    st.markdown(f"{sev_icon.get(w.severity, '⚪')} **{w.code}** — {w.message}")
                    if w.affected:
                        st.caption("Affected: " + ", ".join(w.affected))


# ================== Tab 6: Dividends ==================

with tab_divs:
    if data.dividends.empty:
        st.info("📄 This tab needs `dividends.csv`.")
    else:
        divs = data.dividends.copy()
        divs["date"] = pd.to_datetime(divs["date"], errors="coerce")
        divs = divs.dropna(subset=["date"])
        divs["amount"] = pd.to_numeric(divs["amount"], errors="coerce")
        divs["fy"] = divs["date"].apply(fifo.fy_label)

        c1, c2 = st.columns(2)
        c1.metric("Total dividends", _fmt_inr(divs["amount"].sum()))
        c2.metric("This FY", _fmt_inr(divs.loc[divs["fy"] == fifo.fy_label(pd.Timestamp(date.today())), "amount"].sum()))

        monthly = divs.copy()
        monthly["month"] = monthly["date"].dt.to_period("M").astype(str)
        agg = monthly.groupby("month")["amount"].sum().reset_index()
        fig = px.bar(agg, x="month", y="amount", title="Dividends by month",
                     color_discrete_sequence=["#16a085"])
        fig.update_layout(height=280, margin=dict(t=30, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

        per_asset = divs.groupby("symbol_or_isin").agg(
            total=("amount", "sum"), events=("amount", "count"),
        ).reset_index().sort_values("total", ascending=False)

        pos_invested = positions.set_index("identifier")["invested"].to_dict()
        per_asset["invested"] = per_asset["symbol_or_isin"].map(pos_invested)
        per_asset["yield_on_cost_pct"] = per_asset.apply(
            lambda r: (r["total"] / r["invested"] * 100.0) if r["invested"] and r["invested"] > 0 else None,
            axis=1,
        )
        st.dataframe(per_asset, hide_index=True, use_container_width=True,
                     column_config={
                         "total": st.column_config.NumberColumn("Total", format="₹%.0f"),
                         "invested": st.column_config.NumberColumn("Invested", format="₹%.0f"),
                         "yield_on_cost_pct": st.column_config.NumberColumn("YoC %", format="%.2f%%"),
                     })

        with st.expander("FY totals"):
            st.dataframe(divs.groupby("fy")["amount"].sum().reset_index(), hide_index=True, use_container_width=True)


# ================== Tab 7: Watchlist ==================

with tab_watch:
    if data.watchlist.empty:
        st.info("📄 This tab needs `watchlist.csv`.")
    else:
        wl = data.watchlist.copy()
        stock_price_map = prices.stock_prices.set_index("symbol").to_dict("index") if not prices.stock_prices.empty else {}
        mf_price_map = prices.mf_prices.set_index("isin").to_dict("index") if not prices.mf_prices.empty else {}

        rows: list[dict] = []
        for _, r in wl.iterrows():
            key = str(r["symbol_or_isin"]).strip().upper()
            at = str(r["asset_type"]).strip().lower()
            if at == "stock":
                p = stock_price_map.get(key, {})
                ltp = p.get("ltp"); high = p.get("high_52w"); low = p.get("low_52w")
                dc = p.get("day_change_pct")
                rows.append({
                    "type": "stock", "symbol": key, "name": key,
                    "ltp": ltp, "day_change_pct": dc,
                    "high_52w": high, "low_52w": low,
                    "pct_from_high": ((ltp - high) / high * 100.0) if (ltp and high) else None,
                    "pct_from_low": ((ltp - low) / low * 100.0) if (ltp and low) else None,
                    "note": r.get("note"),
                })
            else:
                p = mf_price_map.get(key, {})
                nav = p.get("nav")
                rows.append({
                    "type": "mutual_fund", "symbol": key, "name": p.get("scheme_name") or key,
                    "ltp": nav, "day_change_pct": None, "high_52w": None, "low_52w": None,
                    "pct_from_high": None, "pct_from_low": None, "note": r.get("note"),
                })

        st.dataframe(
            pd.DataFrame(rows), hide_index=True, use_container_width=True,
            column_config={
                "ltp": st.column_config.NumberColumn("LTP", format="₹%.2f"),
                "day_change_pct": st.column_config.NumberColumn("Day %", format="%.2f%%"),
                "high_52w": st.column_config.NumberColumn("52w High", format="₹%.2f"),
                "low_52w": st.column_config.NumberColumn("52w Low", format="₹%.2f"),
                "pct_from_high": st.column_config.NumberColumn("% from 52w High", format="%.2f%%"),
                "pct_from_low": st.column_config.NumberColumn("% from 52w Low", format="%.2f%%"),
            },
        )

        with st.expander("Add to watchlist"):
            wf1, wf2, wf3 = st.columns([3, 2, 3])
            new_sym = wf1.text_input("Symbol or ISIN")
            new_type = wf2.selectbox("Asset type", ["stock", "mutual_fund"])
            new_note = wf3.text_input("Note")
            if st.button("Append to watchlist.csv", disabled=not new_sym.strip()):
                watch_path = settings.portfolio_data_dir / "watchlist.csv"
                new_row = pd.DataFrame([{
                    "symbol_or_isin": new_sym.strip().upper(),
                    "asset_type": new_type,
                    "note": new_note.strip(),
                }])
                if watch_path.exists() and watch_path.stat().st_size > 0:
                    existing = pd.read_csv(watch_path)
                    out = pd.concat([existing, new_row], ignore_index=True)
                else:
                    out = new_row
                out.to_csv(watch_path, index=False)
                st.success(f"Added {new_sym.strip().upper()}. Click Reload files.")
