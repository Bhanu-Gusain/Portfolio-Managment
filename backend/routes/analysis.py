"""Analysis routes: scores, risks."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas import ScoreOut, WarningOut
from db.repositories import scores_repo, snapshots_repo

router = APIRouter()


@router.get("/scores", response_model=list[ScoreOut])
def scores() -> list[ScoreOut]:
    return [ScoreOut(**s) for s in scores_repo.latest_scores()]


@router.get("/risks", response_model=list[WarningOut])
def risks() -> list[WarningOut]:
    snap = snapshots_repo.latest_snapshot()
    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot yet — run pipeline first.")
    return [WarningOut(**w) for w in snap["payload"].get("warnings", [])]


@router.get("/snapshot")
def snapshot() -> dict:
    snap = snapshots_repo.latest_snapshot()
    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot yet — run pipeline first.")
    return snap
