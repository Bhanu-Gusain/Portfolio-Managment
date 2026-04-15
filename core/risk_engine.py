"""Portfolio risk warnings. Pure function over positions + scores + sector map."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RiskWarning:
    code: str
    severity: str  # low | med | high
    message: str
    affected_symbols: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


MAX_STOCKS = 18
MAX_STOCK_PCT = 12.0
MAX_SECTOR_PCT = 25.0
MIN_STOCK_PCT = 3.0
LOW_SCORE_THRESHOLD = 4.0
LOW_SCORE_BLOAT_PCT = 30.0


def evaluate(positions: list[dict], scores: dict[str, float], sector_map: dict[str, str | None]) -> list[RiskWarning]:
    warnings: list[RiskWarning] = []
    if not positions:
        return warnings

    n = len(positions)
    if n > MAX_STOCKS:
        warnings.append(RiskWarning(
            code="TOO_MANY_HOLDINGS",
            severity="high",
            message=f"Holding {n} stocks; recommended max {MAX_STOCKS}.",
            affected_symbols=[p["symbol"] for p in positions],
        ))

    sector_pct: dict[str, float] = defaultdict(float)
    sector_symbols: dict[str, list[str]] = defaultdict(list)
    for p in positions:
        sec = sector_map.get(p["symbol"]) or "Unknown"
        sector_pct[sec] += p["allocation_pct"]
        sector_symbols[sec].append(p["symbol"])

    for sec, pct in sector_pct.items():
        if pct > MAX_SECTOR_PCT:
            warnings.append(RiskWarning(
                code="SECTOR_CONCENTRATION",
                severity="high",
                message=f"Sector '{sec}' at {pct:.1f}% (> {MAX_SECTOR_PCT}%).",
                affected_symbols=sector_symbols[sec],
            ))

    over = [p["symbol"] for p in positions if p["allocation_pct"] > MAX_STOCK_PCT]
    if over:
        warnings.append(RiskWarning(
            code="STOCK_CONCENTRATION",
            severity="med",
            message=f"{len(over)} position(s) above {MAX_STOCK_PCT}% allocation cap.",
            affected_symbols=over,
        ))

    bloat_capital = sum(
        p["allocation_pct"] for p in positions
        if scores.get(p["symbol"], 10) < LOW_SCORE_THRESHOLD
    )
    if bloat_capital > LOW_SCORE_BLOAT_PCT:
        affected = [p["symbol"] for p in positions if scores.get(p["symbol"], 10) < LOW_SCORE_THRESHOLD]
        warnings.append(RiskWarning(
            code="LOW_SCORE_BLOAT",
            severity="high",
            message=f"{bloat_capital:.1f}% of capital in score<{LOW_SCORE_THRESHOLD} stocks.",
            affected_symbols=affected,
        ))

    underweight = [p["symbol"] for p in positions if p["allocation_pct"] < MIN_STOCK_PCT]
    if underweight:
        warnings.append(RiskWarning(
            code="UNDERWEIGHT_POSITIONS",
            severity="low",
            message=f"{len(underweight)} position(s) below {MIN_STOCK_PCT}% — consider consolidating.",
            affected_symbols=underweight,
        ))

    return warnings


def overall_severity(warnings: list[RiskWarning]) -> str:
    if any(w.severity == "high" for w in warnings):
        return "high"
    if any(w.severity == "med" for w in warnings):
        return "med"
    if warnings:
        return "low"
    return "ok"
