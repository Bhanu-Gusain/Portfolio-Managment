from __future__ import annotations

from pathlib import Path

import pytest

from services.csv_parser import UnmappedSymbolError, parse_groww_csv


SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_groww_holdings.csv"


def test_parse_sample_csv():
    holdings = parse_groww_csv(SAMPLE)
    assert len(holdings) == 12
    relax = {h.symbol for h in holdings}
    assert "RELIANCE.NS" in relax
    assert "HDFCBANK.NS" in relax
    for h in holdings:
        assert h.quantity > 0
        assert h.avg_cost > 0


def test_unmapped_name_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Stock Name,Quantity,Average buy price\nMade Up Co Ltd,1,100\n")
    with pytest.raises(UnmappedSymbolError):
        parse_groww_csv(bad)


def test_missing_columns_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError):
        parse_groww_csv(bad)
