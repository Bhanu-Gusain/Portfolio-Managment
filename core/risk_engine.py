"""Portfolio risk warnings — pure function over a positions DataFrame + sector map."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class RiskWarning:
    code: str
    severity: str  # low | med | high
    message: str
    affected: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


MAX_STOCKS = 18
MAX_SINGLE_WEIGHT = 12.0
MAX_SECTOR_WEIGHT = 25.0
MIN_SINGLE_WEIGHT = 3.0


def evaluate(
    positions: pd.DataFrame,
    sector_map: dict[str, str] | None = None,
) -> list[RiskWarning]:
    if positions.empty:
        return []
    sector_map = sector_map or {}
    warnings: list[RiskWarning] = []

    stock_positions = positions[positions["asset_type"] == "stock"]
    if len(stock_positions) > MAX_STOCKS:
        warnings.append(RiskWarning(
            code="TOO_MANY_HOLDINGS",
            severity="high",
            message=f"{len(stock_positions)} stock holdings (recommended max {MAX_STOCKS}).",
            affected=stock_positions["identifier"].tolist(),
        ))

    # Sector concentration for stocks only
    sector_pct: dict[str, float] = defaultdict(float)
    sector_syms: dict[str, list[str]] = defaultdict(list)
    for _, r in stock_positions.iterrows():
        if pd.isna(r["weight_pct"]):
            continue
        sec = sector_map.get(r["identifier"], "Unknown")
        sector_pct[sec] += float(r["weight_pct"])
        sector_syms[sec].append(r["identifier"])
    for sec, pct in sector_pct.items():
        if pct > MAX_SECTOR_WEIGHT:
            warnings.append(RiskWarning(
                code="SECTOR_CONCENTRATION",
                severity="high",
                message=f"Sector '{sec}' at {pct:.1f}% (> {MAX_SECTOR_WEIGHT}%).",
                affected=sector_syms[sec],
            ))

    over = positions.loc[
        positions["weight_pct"].fillna(0) > MAX_SINGLE_WEIGHT, "identifier"
    ].tolist()
    if over:
        warnings.append(RiskWarning(
            code="STOCK_CONCENTRATION",
            severity="med",
            message=f"{len(over)} position(s) above {MAX_SINGLE_WEIGHT}% weight cap.",
            affected=over,
        ))

    under = positions.loc[
        (positions["weight_pct"].fillna(0) > 0) &
        (positions["weight_pct"].fillna(0) < MIN_SINGLE_WEIGHT),
        "identifier",
    ].tolist()
    if under:
        warnings.append(RiskWarning(
            code="UNDERWEIGHT_POSITIONS",
            severity="low",
            message=f"{len(under)} position(s) below {MIN_SINGLE_WEIGHT}% — consider consolidating.",
            affected=under,
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
