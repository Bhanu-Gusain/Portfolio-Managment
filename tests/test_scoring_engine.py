from __future__ import annotations

from core.scoring_engine import (
    DEFAULT_FACTORS,
    FactorContext,
    ScoringEngine,
    Vs52WHighFactor,
)


def _ctx(**kw):
    base = dict(symbol="TEST.NS", technicals=None, fundamentals=None, sector=None, sector_3m_return=None)
    base.update(kw)
    return FactorContext(**base)


def test_default_factors_sum_to_ten():
    total = sum(f.max_points for f in DEFAULT_FACTORS)
    assert total == 10.0


def test_perfect_score():
    engine = ScoringEngine()
    ctx = _ctx(
        technicals={"trend_label": "strong_up", "close": 100, "high_52w": 100},
        fundamentals={"roe": 25, "sales_growth_3y": 20, "debt_to_equity": 0.4},
        sector="IT",
        sector_3m_return=0.10,
    )
    result = engine.score(ctx)
    assert result.score == 10.0
    assert result.label == "STRONG_BUY"


def test_zero_score():
    engine = ScoringEngine()
    ctx = _ctx(
        technicals={"trend_label": "down", "close": 50, "high_52w": 100},
        fundamentals={"roe": 5, "sales_growth_3y": 2, "debt_to_equity": 2.0},
        sector="X",
        sector_3m_return=-0.20,
    )
    result = engine.score(ctx)
    assert result.score == 0.0
    assert result.label == "AVOID"


def test_missing_fundamentals_graceful():
    engine = ScoringEngine()
    ctx = _ctx(technicals={"trend_label": "up", "close": 90, "high_52w": 100}, fundamentals=None)
    result = engine.score(ctx)
    assert 0 <= result.score <= 10
    # vs52 within 15% (1) + trend up (1.5) = 2.5/10
    assert result.score == 2.5


def test_vs_52w_thresholds():
    f = Vs52WHighFactor()
    assert f.score(_ctx(technicals={"close": 96, "high_52w": 100})).points == 2.0
    assert f.score(_ctx(technicals={"close": 90, "high_52w": 100})).points == 1.0
    assert f.score(_ctx(technicals={"close": 70, "high_52w": 100})).points == 0.0
