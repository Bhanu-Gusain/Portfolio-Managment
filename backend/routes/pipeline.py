"""Pipeline route — kick off the daily batch."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas import PipelineRunOut
from services.pipeline import run_daily_batch

router = APIRouter()


@router.post("/run", response_model=PipelineRunOut)
def run() -> PipelineRunOut:
    try:
        snap_id = run_daily_batch()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PipelineRunOut(snapshot_id=snap_id)
