"""AI explanation routes — wraps Ollama narrative engine."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas import AiOut, ExplainIn
from core import ai_engine
from db.repositories import prices_repo, scores_repo, snapshots_repo

router = APIRouter()


@router.post("/portfolio", response_model=AiOut)
def portfolio() -> AiOut:
    snap = snapshots_repo.latest_snapshot()
    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot — run pipeline first.")
    try:
        return AiOut(text=ai_engine.analyze_portfolio(snap["payload"]))
    except ai_engine.OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/explain", response_model=AiOut)
def explain(body: ExplainIn) -> AiOut:
    score = scores_repo.get_score(body.symbol)
    tech = prices_repo.latest_indicators(body.symbol)
    if not score or not tech:
        raise HTTPException(status_code=404, detail=f"No score/technical data for {body.symbol}")
    try:
        text = ai_engine.explain_stock(body.symbol, score["score"], score["factor_breakdown"], tech)
    except ai_engine.OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AiOut(text=text)


@router.post("/rebalance", response_model=AiOut)
def rebalance() -> AiOut:
    from core.allocation_engine import suggest_rebalance
    from core.portfolio_engine import compute_positions, portfolio_summary

    snap = snapshots_repo.latest_snapshot()
    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot — run pipeline first.")

    try:
        positions = compute_positions()
        summary = portfolio_summary()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    score_map = {s["symbol"]: s["score"] for s in snap["payload"].get("scores", [])}
    label_map = snap["payload"].get("labels") or {s["symbol"]: s["label"] for s in snap["payload"].get("scores", [])}
    actions = suggest_rebalance(
        [p.as_dict() for p in positions], score_map, label_map, summary["total_value"]
    )
    try:
        text = ai_engine.suggest_rebalance(
            [p.as_dict() for p in positions], [a.as_dict() for a in actions]
        )
    except ai_engine.OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AiOut(text=text)
