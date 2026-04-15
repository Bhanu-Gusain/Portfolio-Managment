"""Allocation rebalance engine. Pure function — outputs proposed actions, never executes."""
from __future__ import annotations

from dataclasses import asdict, dataclass

MAX_STOCKS = 18
MAX_PCT = 12.0
MIN_PCT = 3.0


@dataclass(frozen=True)
class RebalanceAction:
    symbol: str
    action: str  # TRIM | EXIT | ADD | HOLD
    current_pct: float
    target_pct: float
    delta_value: float  # rupees, signed (+ buy, - sell)
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def suggest_rebalance(
    positions: list[dict],
    scores: dict[str, float],
    labels: dict[str, str],
    total_value: float,
) -> list[RebalanceAction]:
    """positions[i] = {symbol, current_value, allocation_pct, ...}."""
    if not positions or total_value <= 0:
        return []

    actions: list[RebalanceAction] = []
    freed_pct = 0.0

    # 1) EXIT AVOID/SELL
    keepers: list[dict] = []
    for p in positions:
        lbl = labels.get(p["symbol"], "HOLD")
        if lbl in ("AVOID", "SELL"):
            actions.append(RebalanceAction(
                symbol=p["symbol"],
                action="EXIT",
                current_pct=p["allocation_pct"],
                target_pct=0.0,
                delta_value=-p["current_value"],
                reason=f"label={lbl}",
            ))
            freed_pct += p["allocation_pct"]
        else:
            keepers.append(p)

    # 2) TRIM positions over MAX_PCT
    for p in keepers:
        if p["allocation_pct"] > MAX_PCT:
            target = MAX_PCT
            delta_pct = p["allocation_pct"] - target
            freed_pct += delta_pct
            delta_value = -(delta_pct / 100.0) * total_value
            actions.append(RebalanceAction(
                symbol=p["symbol"],
                action="TRIM",
                current_pct=p["allocation_pct"],
                target_pct=target,
                delta_value=delta_value,
                reason=f"above {MAX_PCT}% cap",
            ))

    # 3) Distribute freed capital to STRONG_BUY / ADD positions
    add_candidates = [
        p for p in keepers
        if labels.get(p["symbol"], "HOLD") in ("STRONG_BUY", "ADD")
        and p["allocation_pct"] < MAX_PCT
    ]
    if add_candidates and freed_pct > 0:
        weights_total = sum(scores.get(p["symbol"], 0) for p in add_candidates)
        if weights_total > 0:
            for p in add_candidates:
                w = scores.get(p["symbol"], 0) / weights_total
                add_pct = freed_pct * w
                target = min(p["allocation_pct"] + add_pct, MAX_PCT)
                if target - p["allocation_pct"] < 0.1:
                    continue
                delta_value = ((target - p["allocation_pct"]) / 100.0) * total_value
                actions.append(RebalanceAction(
                    symbol=p["symbol"],
                    action="ADD",
                    current_pct=p["allocation_pct"],
                    target_pct=round(target, 2),
                    delta_value=delta_value,
                    reason=f"score={scores.get(p['symbol'], 0):.1f}, label={labels.get(p['symbol'])}",
                ))

    # 4) HOLD note for everything else (only if no other action exists for it)
    acted_symbols = {a.symbol for a in actions}
    for p in keepers:
        if p["symbol"] not in acted_symbols:
            actions.append(RebalanceAction(
                symbol=p["symbol"],
                action="HOLD",
                current_pct=p["allocation_pct"],
                target_pct=p["allocation_pct"],
                delta_value=0.0,
                reason=f"label={labels.get(p['symbol'], 'HOLD')}",
            ))

    return actions
