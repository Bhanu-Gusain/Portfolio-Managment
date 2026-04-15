"""Daily action routes."""
from __future__ import annotations

from fastapi import APIRouter

from backend.schemas import SignalOut
from db.repositories import signals_repo

router = APIRouter()


@router.get("/daily", response_model=list[SignalOut])
def daily(date: str | None = None) -> list[SignalOut]:
    return [SignalOut(**s) for s in signals_repo.get_signals(date)]
