"""Daily batch pipeline. Orchestrates fetch → indicators → fundamentals → scores → signals → snapshot.

Mutual funds are priced (NAV from AMFI) but skip technicals, fundamentals, and scoring —
they contribute to portfolio value/allocation but not to per-stock signals.
"""
from __future__ import annotations

from collections import defaultdict

from core import action_engine, portfolio_engine, risk_engine
from core.scoring_engine import FactorContext, ScoringEngine
from core.technical_engine import compute as compute_tech
from data_layer import cache as price_cache
from data_layer import fundamentals as fundamentals_module
from db.repositories import audit_repo, holdings_repo, prices_repo, scores_repo, snapshots_repo
from utils.config import PROJECT_ROOT
from utils.logging import get_logger
from utils.time import today_iso

log = get_logger(__name__)

WATCHLIST_PATH = PROJECT_ROOT / "data" / "watchlist.csv"


def _load_watchlist() -> list[str]:
    if not WATCHLIST_PATH.exists():
        return []
    out: list[str] = []
    for line in WATCHLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower() == "symbol":
            continue
        out.append(line)
    return out


def _sector_returns(symbols: list[str]) -> dict[str, float]:
    by_sector: dict[str, list[float]] = defaultdict(list)
    for sym in symbols:
        meta = holdings_repo.get_stock_meta(sym) or {}
        sec = meta.get("sector") or "Unknown"
        df = prices_repo.load_prices(sym)
        if df.empty or len(df) < 65:
            continue
        recent = df["close"].iloc[-1]
        past = df["close"].iloc[-63]
        if past > 0:
            by_sector[sec].append(float((recent - past) / past))
    out: dict[str, float] = {}
    for sec, returns in by_sector.items():
        if returns:
            sorted_r = sorted(returns)
            mid = len(sorted_r) // 2
            out[sec] = sorted_r[mid] if len(sorted_r) % 2 == 1 else (sorted_r[mid - 1] + sorted_r[mid]) / 2
    return out


def _is_mf(symbol: str) -> bool:
    meta = holdings_repo.get_stock_meta(symbol) or {}
    return (meta.get("asset_type") or "stock") == "mutual_fund"


def run_daily_batch() -> int:
    portfolio_symbols = holdings_repo.list_symbols()
    watchlist = _load_watchlist()
    universe = sorted(set(portfolio_symbols) | set(watchlist))

    if not universe:
        raise RuntimeError("No symbols to process: portfolio empty and watchlist empty.")

    log.info("Running daily batch on %d symbols", len(universe))

    # 1. Prices (yfinance for stocks, AMFI NAV for MFs — cache.py routes by asset_type)
    prices = price_cache.get_or_fetch(universe)

    # 2. Technicals (stocks only)
    today = today_iso()
    tech_snapshots: dict[str, dict] = {}
    stock_universe = [s for s in universe if not _is_mf(s)]
    mf_universe = [s for s in universe if _is_mf(s)]
    for sym in stock_universe:
        df = prices.get(sym)
        if df is None or df.empty:
            continue
        try:
            snap = compute_tech(df)
        except ValueError as exc:
            log.warning("Skipping technicals for %s: %s", sym, exc)
            continue
        prices_repo.upsert_indicators(sym, snap.date, snap.as_dict())
        tech_snapshots[sym] = snap.as_dict()

    # 3. Fundamentals (stocks only)
    fundamentals_module.refresh(stock_universe)

    # 4. Sector context (stocks only)
    sector_returns = _sector_returns(stock_universe)

    # 5. Scoring (stocks only)
    engine = ScoringEngine()
    for sym in stock_universe:
        meta = holdings_repo.get_stock_meta(sym) or {}
        sector = meta.get("sector")
        ctx = FactorContext(
            symbol=sym,
            technicals=tech_snapshots.get(sym),
            fundamentals=prices_repo.get_fundamentals(sym),
            sector=sector,
            sector_3m_return=sector_returns.get(sector or "Unknown"),
        )
        result = engine.score(ctx)
        scores_repo.upsert_score(sym, today, result.score, result.label, result.breakdown)

    # 6. Daily actions (stocks only — MFs don't get trade signals)
    actions = action_engine.generate(stock_universe)

    # 7. Risk + snapshot
    snapshot_payload = _build_snapshot_payload(universe, actions, mf_universe)
    snap_id = snapshots_repo.insert_snapshot(
        total_value=snapshot_payload["summary"]["total_value"],
        total_pnl=snapshot_payload["summary"]["total_pnl"],
        portfolio_score=snapshot_payload["summary"]["portfolio_score"],
        payload=snapshot_payload,
    )
    log.info("Snapshot %d written", snap_id)
    audit_repo.log("pipeline_run", f"snapshot_id={snap_id} symbols={len(universe)}")
    return snap_id


def _build_snapshot_payload(universe: list[str], actions: list, mf_universe: list[str]) -> dict:
    portfolio_symbols = holdings_repo.list_symbols()
    if not portfolio_symbols:
        summary = {
            "total_value": 0.0, "total_cost": 0.0, "total_pnl": 0.0,
            "pnl_pct": 0.0, "num_positions": 0, "portfolio_score": 0.0,
        }
        return {
            "summary": summary, "positions": [],
            "scores": scores_repo.latest_scores(), "warnings": [],
            "actions": [a.as_dict() for a in actions],
            "mutual_fund_symbols": mf_universe,
        }

    positions = portfolio_engine.compute_positions()
    summary = portfolio_engine.portfolio_summary()

    latest = scores_repo.latest_scores()
    score_map = {s["symbol"]: s["score"] for s in latest}
    label_map = {s["symbol"]: s["label"] for s in latest}

    sector_map: dict[str, str | None] = {}
    for p in positions:
        meta = holdings_repo.get_stock_meta(p.symbol) or {}
        sector_map[p.symbol] = meta.get("sector")

    pos_dicts = [p.as_dict() for p in positions]

    # Risk engine ignores MF positions — they don't contribute to sector/stock concentration.
    stock_pos = [p for p in pos_dicts if (holdings_repo.get_stock_meta(p["symbol"]) or {}).get("asset_type", "stock") != "mutual_fund"]
    warnings = risk_engine.evaluate(stock_pos, score_map, sector_map)

    # Portfolio score = allocation-weighted avg across stocks that were scored.
    weighted_score = 0.0
    for p in positions:
        if p.symbol in score_map:
            weighted_score += (p.allocation_pct / 100.0) * score_map[p.symbol]
    summary["portfolio_score"] = round(weighted_score, 2)

    return {
        "summary": summary,
        "positions": pos_dicts,
        "scores": latest,
        "labels": label_map,
        "sector_map": sector_map,
        "warnings": [w.as_dict() for w in warnings],
        "overall_severity": risk_engine.overall_severity(warnings),
        "actions": [a.as_dict() for a in actions],
        "mutual_fund_symbols": mf_universe,
    }
