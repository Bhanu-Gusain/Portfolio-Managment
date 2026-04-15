"""Streamlit dashboard. Reads everything from SQLite — never triggers compute on render.

Tabs: Overview / Holdings / Scoring / Risk / Actions / AI Insights.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import tempfile

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import ai_engine
from core.allocation_engine import suggest_rebalance
from core.portfolio_engine import compute_positions, portfolio_summary
from db.init_db import init_db
from db.repositories import holdings_repo, prices_repo, scores_repo, signals_repo, snapshots_repo
from services.csv_parser import UnmappedSymbolError, parse_groww_csv
from services.pipeline import run_daily_batch

st.set_page_config(page_title="AI Investment Engine", layout="wide", initial_sidebar_state="collapsed")
init_db()


# ---------- helpers ----------

@st.cache_data(ttl=30)
def _summary() -> dict:
    try:
        return portfolio_summary()
    except RuntimeError:
        return {"total_value": 0, "total_cost": 0, "total_pnl": 0, "pnl_pct": 0, "num_positions": 0}


@st.cache_data(ttl=30)
def _positions_df() -> pd.DataFrame:
    try:
        return pd.DataFrame([p.as_dict() for p in compute_positions()])
    except RuntimeError:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def _scores_df() -> pd.DataFrame:
    rows = scores_repo.latest_scores()
    if not rows:
        return pd.DataFrame()
    out = []
    for r in rows:
        out.append({
            "symbol": r["symbol"],
            "score": r["score"],
            "label": r["label"],
            "factors": r["factor_breakdown"],
        })
    return pd.DataFrame(out)


@st.cache_data(ttl=30)
def _signals_df() -> pd.DataFrame:
    return pd.DataFrame(signals_repo.get_signals())


@st.cache_data(ttl=30)
def _snapshot() -> dict | None:
    return snapshots_repo.latest_snapshot()


def _bust_caches() -> None:
    _summary.clear()
    _positions_df.clear()
    _scores_df.clear()
    _signals_df.clear()
    _snapshot.clear()


# ---------- header / actions ----------

st.title("AI Investment Decision Engine")
st.caption("Local-first quant analysis for Indian portfolios — engines decide, AI explains.")

with st.sidebar:
    st.header("Actions")
    uploaded = st.file_uploader("Upload Groww CSV", type=["csv"])
    if uploaded is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded.read())
            path = Path(tmp.name)
        try:
            parsed = parse_groww_csv(path)
            for h in parsed:
                holdings_repo.upsert_stock(h.symbol, h.name)
            n = holdings_repo.replace_holdings([(h.symbol, h.quantity, h.avg_cost) for h in parsed])
            _bust_caches()
            st.success(f"Loaded {n} holdings.")
        except UnmappedSymbolError as exc:
            st.error(str(exc))
        except (ValueError, FileNotFoundError) as exc:
            st.error(f"Parse error: {exc}")
        finally:
            path.unlink(missing_ok=True)

    if st.button("Run Daily Batch", type="primary", use_container_width=True):
        with st.spinner("Fetching prices, computing indicators, scoring..."):
            try:
                snap_id = run_daily_batch()
                _bust_caches()
                st.success(f"Snapshot {snap_id} written.")
            except RuntimeError as exc:
                st.error(str(exc))


tabs = st.tabs(["Overview", "Holdings", "Scoring", "Risk", "Actions", "AI Insights"])


# ---------- Tab 1: Overview ----------
with tabs[0]:
    s = _summary()
    snap = _snapshot()
    pf_score = (snap or {}).get("portfolio_score") or 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total value", f"₹{s['total_value']:,.0f}")
    c2.metric("Total P&L", f"₹{s['total_pnl']:,.0f}", f"{s['pnl_pct']:+.2f}%")
    c3.metric("Holdings", s["num_positions"])
    c4.metric("Portfolio score", f"{pf_score:.2f}/10")

    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=pf_score,
            gauge={
                "axis": {"range": [0, 10]},
                "bar": {"color": "#1f77b4"},
                "steps": [
                    {"range": [0, 4], "color": "#e74c3c"},
                    {"range": [4, 6], "color": "#f39c12"},
                    {"range": [6, 10], "color": "#2ecc71"},
                ],
            },
            title={"text": "Portfolio Score"},
        )
    )
    gauge.update_layout(height=300, margin=dict(t=40, b=10, l=10, r=10))
    st.plotly_chart(gauge, use_container_width=True)

    if snap:
        st.caption(f"Last snapshot: {snap['taken_at']}")


# ---------- Tab 2: Holdings ----------
with tabs[1]:
    pos = _positions_df()
    if pos.empty:
        st.info("Upload a holdings CSV in the sidebar to begin.")
    else:
        snap = _snapshot() or {"payload": {}}
        sector_map = snap.get("payload", {}).get("sector_map", {})
        pos["sector"] = pos["symbol"].map(lambda s: sector_map.get(s) or "Unknown")

        st.dataframe(
            pos[["symbol", "sector", "quantity", "avg_cost", "last_price",
                 "current_value", "pnl", "pnl_pct", "allocation_pct"]],
            use_container_width=True,
            hide_index=True,
        )

        col1, col2 = st.columns(2)
        sector_pct = pos.groupby("sector")["allocation_pct"].sum().reset_index()
        col1.plotly_chart(
            px.pie(sector_pct, names="sector", values="allocation_pct", title="Sector allocation"),
            use_container_width=True,
        )
        col2.plotly_chart(
            px.pie(pos, names="symbol", values="allocation_pct", title="Stock allocation"),
            use_container_width=True,
        )
        st.plotly_chart(
            px.bar(
                pos.sort_values("allocation_pct", ascending=False),
                x="symbol", y="allocation_pct",
                title="Allocation by stock", color="allocation_pct",
                color_continuous_scale="blues",
            ),
            use_container_width=True,
        )


# ---------- Tab 3: Scoring ----------
with tabs[2]:
    sc = _scores_df()
    if sc.empty:
        st.info("Run the daily batch to generate scores.")
    else:
        pos = _positions_df()
        merged = sc.merge(
            pos[["symbol", "allocation_pct"]] if not pos.empty else pd.DataFrame({"symbol": [], "allocation_pct": []}),
            on="symbol", how="left",
        )
        merged["allocation_pct"] = merged["allocation_pct"].fillna(0)

        col1, col2 = st.columns(2)
        col1.plotly_chart(
            px.histogram(sc, x="score", nbins=10, title="Score distribution",
                         color="label",
                         category_orders={"label": ["AVOID", "SELL", "HOLD", "ADD", "STRONG_BUY"]}),
            use_container_width=True,
        )
        col2.plotly_chart(
            px.scatter(merged, x="score", y="allocation_pct", color="label",
                       hover_name="symbol", size="allocation_pct",
                       title="Score vs Allocation"),
            use_container_width=True,
        )

        # trend pie from technicals
        trend_rows = []
        for sym in sc["symbol"]:
            ind = prices_repo.latest_indicators(sym)
            if ind:
                trend_rows.append({"symbol": sym, "trend": ind.get("trend_label") or "weak"})
        if trend_rows:
            td = pd.DataFrame(trend_rows)
            st.plotly_chart(
                px.pie(td, names="trend", title="Trend classification"),
                use_container_width=True,
            )

        def _color(label: str) -> str:
            return {
                "STRONG_BUY": "#2ecc71",
                "ADD": "#27ae60",
                "HOLD": "#7f8c8d",
                "SELL": "#e67e22",
                "AVOID": "#e74c3c",
            }.get(label, "#7f8c8d")

        display = sc[["symbol", "score", "label"]].copy()
        display["factors"] = sc["factors"].apply(lambda d: ", ".join(f"{k}:{v['points']}" for k, v in d.items()))
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=10, format="%.2f"),
            },
        )

        with st.expander("Factor breakdown JSON"):
            for _, row in sc.iterrows():
                st.markdown(f"**{row['symbol']}** — {row['label']} ({row['score']:.2f})")
                st.json(row["factors"])


# ---------- Tab 4: Risk ----------
with tabs[3]:
    snap = _snapshot()
    if not snap:
        st.info("Run the daily batch to evaluate risk.")
    else:
        sev = snap["payload"].get("overall_severity", "ok")
        sev_color = {"high": "#e74c3c", "med": "#f39c12", "low": "#3498db", "ok": "#2ecc71"}[sev]
        st.markdown(
            f"<div style='padding:18px;border-radius:8px;background:{sev_color};color:white;"
            f"font-size:22px;font-weight:600;text-align:center;'>Overall risk: {sev.upper()}</div>",
            unsafe_allow_html=True,
        )
        st.write("")

        warnings = snap["payload"].get("warnings", [])
        if not warnings:
            st.success("No risk warnings.")
        else:
            for w in warnings:
                badge = {"high": "🔴", "med": "🟡", "low": "🔵"}.get(w["severity"], "⚪")
                with st.container(border=True):
                    st.markdown(f"{badge} **{w['code']}** — {w['message']}")
                    if w["affected_symbols"]:
                        st.caption("Affected: " + ", ".join(w["affected_symbols"]))

        # sector concentration chart
        positions = snap["payload"].get("positions", [])
        sector_map = snap["payload"].get("sector_map", {})
        if positions:
            sec_df = pd.DataFrame([
                {"symbol": p["symbol"], "sector": sector_map.get(p["symbol"]) or "Unknown",
                 "allocation_pct": p["allocation_pct"]}
                for p in positions
            ])
            sec_agg = sec_df.groupby("sector")["allocation_pct"].sum().reset_index().sort_values("allocation_pct", ascending=False)
            sec_agg["over_cap"] = sec_agg["allocation_pct"] > 25
            st.plotly_chart(
                px.bar(sec_agg, x="sector", y="allocation_pct",
                       color="over_cap", title="Sector concentration (cap = 25%)",
                       color_discrete_map={True: "#e74c3c", False: "#3498db"}),
                use_container_width=True,
            )


# ---------- Tab 5: Actions ----------
with tabs[4]:
    sigs = _signals_df()
    if sigs.empty:
        st.info("No daily actions yet — run the daily batch.")
    else:
        col_sell, col_add, col_watch = st.columns(3)
        styles = {
            "SELL": ("#fdecea", "#c0392b", col_sell, "SELL"),
            "ADD": ("#e8f8f0", "#1e8449", col_add, "ADD"),
            "WATCH": ("#fef5e7", "#b9770e", col_watch, "WATCH"),
        }
        for action, (bg, fg, col, label) in styles.items():
            with col:
                st.markdown(
                    f"<h3 style='color:{fg}'>{label}</h3>", unsafe_allow_html=True
                )
                rows = sigs[sigs["action"] == action]
                if rows.empty:
                    st.caption("None")
                else:
                    for _, r in rows.iterrows():
                        st.markdown(
                            f"<div style='padding:10px;margin-bottom:8px;border-radius:6px;"
                            f"background:{bg};border-left:4px solid {fg};'>"
                            f"<b>{r['symbol']}</b> &nbsp;<small>score {r['score']:.1f} · {r['trend_label']}</small><br>"
                            f"<span style='font-size:13px;color:#333;'>{r['reason']}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )


# ---------- Tab 6: AI Insights ----------
with tabs[5]:
    snap = _snapshot()
    if not snap:
        st.info("Run the daily batch to enable AI insights.")
    else:
        c1, c2, c3 = st.columns(3)

        if c1.button("Analyze portfolio", use_container_width=True):
            with st.spinner("Querying local LLM..."):
                try:
                    text = ai_engine.analyze_portfolio(snap["payload"])
                    st.markdown(text)
                except ai_engine.OllamaError as exc:
                    st.error(f"Ollama error: {exc}")

        if c2.button("Suggest rebalance", use_container_width=True):
            with st.spinner("Computing rebalance..."):
                try:
                    positions = compute_positions()
                    summary = portfolio_summary()
                    score_map = {s["symbol"]: s["score"] for s in snap["payload"].get("scores", [])}
                    label_map = snap["payload"].get("labels") or {s["symbol"]: s["label"] for s in snap["payload"].get("scores", [])}
                    actions = suggest_rebalance(
                        [p.as_dict() for p in positions], score_map, label_map, summary["total_value"]
                    )
                    st.dataframe(pd.DataFrame([a.as_dict() for a in actions]), use_container_width=True, hide_index=True)
                    text = ai_engine.suggest_rebalance(
                        [p.as_dict() for p in positions], [a.as_dict() for a in actions]
                    )
                    st.markdown(text)
                except (RuntimeError, ai_engine.OllamaError) as exc:
                    st.error(str(exc))

        symbols = [s["symbol"] for s in snap["payload"].get("scores", [])]
        sym = c3.selectbox("Explain stock", symbols) if symbols else None
        if sym and c3.button("Explain", use_container_width=True):
            with st.spinner("Querying local LLM..."):
                try:
                    score = scores_repo.get_score(sym)
                    tech = prices_repo.latest_indicators(sym)
                    text = ai_engine.explain_stock(sym, score["score"], score["factor_breakdown"], tech)
                    st.markdown(text)
                except (ai_engine.OllamaError, KeyError, TypeError) as exc:
                    st.error(str(exc))
