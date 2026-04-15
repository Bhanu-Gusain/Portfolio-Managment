"""Pluggable factor-based scoring engine.

Every factor implements the Factor protocol. The engine sums factor outputs into a 0–10 score and assigns a label. Adding a new factor = create a class + append to DEFAULT_FACTORS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class FactorContext:
    symbol: str
    technicals: dict | None
    fundamentals: dict | None
    sector: str | None
    sector_3m_return: float | None  # median of sector universe; None if unknown


@dataclass(frozen=True)
class FactorResult:
    name: str
    points: float
    max_points: float
    reason: str


class Factor(Protocol):
    name: str
    max_points: float

    def score(self, ctx: FactorContext) -> FactorResult: ...


# ---------- Built-in factors ----------

class TrendStrengthFactor:
    name = "trend_strength"
    max_points = 2.0

    def score(self, ctx: FactorContext) -> FactorResult:
        t = ctx.technicals or {}
        label = (t.get("trend_label") or "weak").lower()
        mapping = {"strong_up": 2.0, "up": 1.5, "weak": 0.5, "down": 0.0}
        pts = mapping.get(label, 0.0)
        return FactorResult(self.name, pts, self.max_points, f"trend={label}")


class Vs52WHighFactor:
    name = "vs_52w_high"
    max_points = 2.0

    def score(self, ctx: FactorContext) -> FactorResult:
        t = ctx.technicals or {}
        close = t.get("close")
        high = t.get("high_52w")
        if close is None or high is None or high == 0:
            return FactorResult(self.name, 0.0, self.max_points, "missing data")
        gap = (high - close) / high
        if gap <= 0.05:
            return FactorResult(self.name, 2.0, self.max_points, f"within 5% of 52w high (gap={gap:.1%})")
        if gap <= 0.15:
            return FactorResult(self.name, 1.0, self.max_points, f"within 15% (gap={gap:.1%})")
        return FactorResult(self.name, 0.0, self.max_points, f"far from 52w high (gap={gap:.1%})")


class RoeFactor:
    name = "roe"
    max_points = 2.0

    def score(self, ctx: FactorContext) -> FactorResult:
        f = ctx.fundamentals or {}
        roe = f.get("roe")
        if roe is None:
            return FactorResult(self.name, 0.0, self.max_points, "ROE missing")
        if roe > 20:
            return FactorResult(self.name, 2.0, self.max_points, f"ROE {roe:.1f}% > 20")
        if roe >= 15:
            return FactorResult(self.name, 1.0, self.max_points, f"ROE {roe:.1f}% in 15–20")
        return FactorResult(self.name, 0.0, self.max_points, f"ROE {roe:.1f}% < 15")


class SalesGrowthFactor:
    name = "sales_growth"
    max_points = 2.0

    def score(self, ctx: FactorContext) -> FactorResult:
        f = ctx.fundamentals or {}
        g = f.get("sales_growth_3y")
        if g is None:
            return FactorResult(self.name, 0.0, self.max_points, "sales growth missing")
        if g > 15:
            return FactorResult(self.name, 2.0, self.max_points, f"sales growth {g:.1f}% > 15")
        if g >= 10:
            return FactorResult(self.name, 1.0, self.max_points, f"sales growth {g:.1f}% in 10–15")
        return FactorResult(self.name, 0.0, self.max_points, f"sales growth {g:.1f}% < 10")


class DebtEquityFactor:
    name = "debt_to_equity"
    max_points = 1.0

    def score(self, ctx: FactorContext) -> FactorResult:
        f = ctx.fundamentals or {}
        de = f.get("debt_to_equity")
        if de is None:
            return FactorResult(self.name, 0.0, self.max_points, "D/E missing")
        if de < 1:
            return FactorResult(self.name, 1.0, self.max_points, f"D/E {de:.2f} < 1")
        return FactorResult(self.name, 0.0, self.max_points, f"D/E {de:.2f} >= 1")


class SectorStrengthFactor:
    name = "sector_strength"
    max_points = 1.0

    def score(self, ctx: FactorContext) -> FactorResult:
        if ctx.sector_3m_return is None:
            return FactorResult(self.name, 0.0, self.max_points, "no sector context")
        if ctx.sector_3m_return > 0:
            return FactorResult(self.name, 1.0, self.max_points, f"{ctx.sector} 3m return {ctx.sector_3m_return:.1%} > 0")
        return FactorResult(self.name, 0.0, self.max_points, f"{ctx.sector} 3m return {ctx.sector_3m_return:.1%} <= 0")


DEFAULT_FACTORS: list[Factor] = [
    TrendStrengthFactor(),
    Vs52WHighFactor(),
    RoeFactor(),
    SalesGrowthFactor(),
    DebtEquityFactor(),
    SectorStrengthFactor(),
]


@dataclass(frozen=True)
class Score:
    symbol: str
    score: float
    label: str
    breakdown: dict


def _label_for(score: float) -> str:
    if score >= 8:
        return "STRONG_BUY"
    if score >= 6:
        return "ADD"
    if score >= 4:
        return "HOLD"
    if score >= 2:
        return "SELL"
    return "AVOID"


class ScoringEngine:
    def __init__(self, factors: list[Factor] | None = None):
        self.factors = factors or DEFAULT_FACTORS
        self.max_total = sum(f.max_points for f in self.factors)
        if abs(self.max_total - 10.0) > 1e-6:
            log.warning("Factor max_points sum to %.2f, not 10.0", self.max_total)

    def score(self, ctx: FactorContext) -> Score:
        results = [f.score(ctx) for f in self.factors]
        total = sum(r.points for r in results)
        # Normalise to 10-pt scale if factors don't sum to 10
        scaled = round(total * (10.0 / self.max_total), 2) if self.max_total else 0.0
        breakdown = {
            r.name: {"points": r.points, "max": r.max_points, "reason": r.reason}
            for r in results
        }
        return Score(symbol=ctx.symbol, score=scaled, label=_label_for(scaled), breakdown=breakdown)
