"""Pydantic response models. Pure DTOs — no business logic."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PositionOut(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    last_price: float
    cost_basis: float
    current_value: float
    pnl: float
    pnl_pct: float
    allocation_pct: float


class PortfolioSummary(BaseModel):
    total_value: float
    total_cost: float
    total_pnl: float
    pnl_pct: float
    num_positions: int


class ScoreOut(BaseModel):
    symbol: str
    date: str
    score: float
    label: str
    factor_breakdown: dict[str, Any]


class SignalOut(BaseModel):
    id: int
    date: str
    symbol: str
    action: str
    reason: str
    score: float | None = None
    trend_label: str | None = None


class WarningOut(BaseModel):
    code: str
    severity: str
    message: str
    affected_symbols: list[str]


class PipelineRunOut(BaseModel):
    snapshot_id: int


class UploadOut(BaseModel):
    holdings_loaded: int


class AiOut(BaseModel):
    text: str


class ExplainIn(BaseModel):
    symbol: str
