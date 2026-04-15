"""Portfolio computation: positions, P&L, allocation %.

Reads holdings + latest prices from DB. Fail loud if a holding has no price.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from db.repositories import holdings_repo, prices_repo
from utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    avg_cost: float
    last_price: float
    cost_basis: float
    current_value: float
    pnl: float
    pnl_pct: float
    allocation_pct: float

    def as_dict(self) -> dict:
        return asdict(self)


def compute_positions() -> list[Position]:
    holdings = holdings_repo.list_holdings()
    if not holdings:
        return []

    raw = []
    for h in holdings:
        price = prices_repo.latest_price(h.symbol)
        if price is None:
            raise RuntimeError(f"No price data for {h.symbol}. Run pipeline before computing positions.")
        raw.append((h, price))

    total_value = sum(h.quantity * p for (h, p) in raw)
    if total_value <= 0:
        raise RuntimeError("Portfolio total value computed as <= 0; check price data.")

    positions: list[Position] = []
    for h, price in raw:
        cost_basis = h.quantity * h.avg_cost
        current_value = h.quantity * price
        pnl = current_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
        alloc = current_value / total_value * 100.0
        positions.append(Position(
            symbol=h.symbol,
            quantity=h.quantity,
            avg_cost=h.avg_cost,
            last_price=price,
            cost_basis=cost_basis,
            current_value=current_value,
            pnl=pnl,
            pnl_pct=pnl_pct,
            allocation_pct=alloc,
        ))

    return sorted(positions, key=lambda p: -p.allocation_pct)


def portfolio_summary() -> dict:
    positions = compute_positions()
    if not positions:
        return {"total_value": 0.0, "total_cost": 0.0, "total_pnl": 0.0, "pnl_pct": 0.0, "num_positions": 0}
    total_value = sum(p.current_value for p in positions)
    total_cost = sum(p.cost_basis for p in positions)
    total_pnl = total_value - total_cost
    pnl_pct = (total_pnl / total_cost * 100.0) if total_cost > 0 else 0.0
    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "pnl_pct": pnl_pct,
        "num_positions": len(positions),
    }
