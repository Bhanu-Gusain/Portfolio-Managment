"""Tests for core.risk_engine."""
from __future__ import annotations

import pandas as pd

from core.risk_engine import evaluate, overall_severity


def _pos(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_empty() -> None:
    assert evaluate(_pos([])) == []


def test_over_concentration_flagged() -> None:
    positions = _pos([
        {"asset_type": "stock", "identifier": "A", "weight_pct": 30.0, "current_value": 30},
        {"asset_type": "stock", "identifier": "B", "weight_pct": 70.0, "current_value": 70},
    ])
    warnings = evaluate(positions, sector_map={"A": "IT", "B": "IT"})
    codes = {w.code for w in warnings}
    assert "STOCK_CONCENTRATION" in codes
    assert "SECTOR_CONCENTRATION" in codes


def test_underweight_flagged() -> None:
    positions = _pos([
        {"asset_type": "stock", "identifier": "A", "weight_pct": 1.0, "current_value": 1},
        {"asset_type": "stock", "identifier": "B", "weight_pct": 99.0, "current_value": 99},
    ])
    warnings = evaluate(positions, sector_map={})
    assert any(w.code == "UNDERWEIGHT_POSITIONS" for w in warnings)


def test_too_many_stocks() -> None:
    positions = _pos([
        {"asset_type": "stock", "identifier": f"S{i}", "weight_pct": 5.0, "current_value": 5.0}
        for i in range(20)
    ])
    warnings = evaluate(positions)
    assert any(w.code == "TOO_MANY_HOLDINGS" for w in warnings)


def test_overall_severity_ordering() -> None:
    from core.risk_engine import RiskWarning
    assert overall_severity([]) == "ok"
    assert overall_severity([RiskWarning("X", "low", "x", [])]) == "low"
    assert overall_severity([RiskWarning("X", "med", "x", [])]) == "med"
    assert overall_severity([
        RiskWarning("X", "low", "x", []),
        RiskWarning("Y", "high", "y", []),
    ]) == "high"
