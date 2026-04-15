from __future__ import annotations

from core.allocation_engine import suggest_rebalance


def test_exits_avoid_labels():
    positions = [
        {"symbol": "BAD.NS", "allocation_pct": 15, "current_value": 15000},
        {"symbol": "GOOD.NS", "allocation_pct": 10, "current_value": 10000},
    ]
    actions = suggest_rebalance(
        positions, {"BAD.NS": 1, "GOOD.NS": 8},
        {"BAD.NS": "AVOID", "GOOD.NS": "STRONG_BUY"}, 100000,
    )
    by_sym = {a.symbol: a for a in actions}
    assert by_sym["BAD.NS"].action == "EXIT"
    assert by_sym["BAD.NS"].target_pct == 0


def test_trims_over_max_pct():
    positions = [
        {"symbol": "BIG.NS", "allocation_pct": 20, "current_value": 20000},
        {"symbol": "SML.NS", "allocation_pct": 6, "current_value": 6000},
    ]
    actions = suggest_rebalance(
        positions, {"BIG.NS": 7, "SML.NS": 8},
        {"BIG.NS": "ADD", "SML.NS": "STRONG_BUY"}, 100000,
    )
    by_sym = {a.symbol: a for a in actions if a.action != "ADD"}
    assert "BIG.NS" in by_sym
    assert by_sym["BIG.NS"].action == "TRIM"
    assert by_sym["BIG.NS"].target_pct == 12


def test_redeploys_to_strong_buys():
    positions = [
        {"symbol": "X.NS", "allocation_pct": 20, "current_value": 20000},
        {"symbol": "Y.NS", "allocation_pct": 5, "current_value": 5000},
        {"symbol": "Z.NS", "allocation_pct": 5, "current_value": 5000},
    ]
    actions = suggest_rebalance(
        positions, {"X.NS": 7, "Y.NS": 9, "Z.NS": 9},
        {"X.NS": "ADD", "Y.NS": "STRONG_BUY", "Z.NS": "STRONG_BUY"}, 100000,
    )
    add_actions = [a for a in actions if a.action == "ADD"]
    assert len(add_actions) >= 1
    assert all(a.delta_value > 0 for a in add_actions)
