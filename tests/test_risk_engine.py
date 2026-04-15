from __future__ import annotations

from core.risk_engine import evaluate, overall_severity


def _pos(symbol: str, alloc: float, value: float = 10000):
    return {"symbol": symbol, "allocation_pct": alloc, "current_value": value}


def test_no_warnings_for_clean_portfolio():
    # 10 stocks at 10% each, spread across 5 sectors (20% each → under 25% cap)
    sectors = ["IT", "Banks", "Auto", "Pharma", "FMCG"]
    positions = [_pos(f"S{i}.NS", 10) for i in range(10)]
    sector_map = {f"S{i}.NS": sectors[i % 5] for i in range(10)}
    scores = {f"S{i}.NS": 7 for i in range(10)}
    warnings = evaluate(positions, scores, sector_map)
    assert overall_severity(warnings) in ("ok", "low")


def test_too_many_holdings():
    positions = [_pos(f"S{i}.NS", 5) for i in range(20)]
    warnings = evaluate(positions, {f"S{i}.NS": 7 for i in range(20)}, {f"S{i}.NS": "IT" for i in range(20)})
    codes = {w.code for w in warnings}
    assert "TOO_MANY_HOLDINGS" in codes


def test_sector_concentration():
    positions = [_pos(f"S{i}.NS", 10) for i in range(10)]
    sector_map = {f"S{i}.NS": "Banks" for i in range(10)}
    warnings = evaluate(positions, {f"S{i}.NS": 7 for i in range(10)}, sector_map)
    assert any(w.code == "SECTOR_CONCENTRATION" for w in warnings)


def test_stock_concentration():
    positions = [_pos("BIG.NS", 25), _pos("SML.NS", 75)]
    warnings = evaluate(positions, {"BIG.NS": 7, "SML.NS": 7}, {"BIG.NS": "IT", "SML.NS": "Auto"})
    assert any(w.code == "STOCK_CONCENTRATION" for w in warnings)


def test_low_score_bloat():
    positions = [_pos("L1.NS", 20), _pos("L2.NS", 20), _pos("G.NS", 60)]
    scores = {"L1.NS": 2, "L2.NS": 3, "G.NS": 8}
    warnings = evaluate(positions, scores, {"L1.NS": "A", "L2.NS": "B", "G.NS": "C"})
    assert any(w.code == "LOW_SCORE_BLOAT" for w in warnings)
