from __future__ import annotations

from pathlib import Path

import pytest

from services.portfolio_loader import (
    UnmappedSymbolError,
    parse_portfolio_file,
)


SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_holdings.csv"


def test_unified_format_splits_stocks_and_mfs():
    holdings = parse_portfolio_file(SAMPLE)
    stocks = [h for h in holdings if h.asset_type == "stock"]
    mfs = [h for h in holdings if h.asset_type == "mutual_fund"]
    assert len(stocks) == 10
    assert len(mfs) == 2
    symbols = {h.symbol for h in stocks}
    assert "RELIANCE.NS" in symbols
    assert "HDFCBANK.NS" in symbols
    isins = {h.symbol for h in mfs}
    assert "INF879O01019" in isins
    assert "INF846K01EW2" in isins


def test_rejects_unknown_extension(tmp_path):
    bad = tmp_path / "holdings.txt"
    bad.write_text("anything")
    with pytest.raises(ValueError):
        parse_portfolio_file(bad)


def test_ticker_pass_through(tmp_path):
    """If the user types a ticker (e.g. RELIANCE.NS) in the name column, use it directly."""
    csv = tmp_path / "tickers.csv"
    csv.write_text("symbol,quantity,avg_cost\nRELIANCE.NS,10,2500\nTCS.NS,5,3300\n")
    holdings = parse_portfolio_file(csv)
    assert {h.symbol for h in holdings} == {"RELIANCE.NS", "TCS.NS"}
    assert all(h.asset_type == "stock" for h in holdings)


def test_mf_inferred_from_columns(tmp_path):
    csv = tmp_path / "mf.csv"
    csv.write_text(
        "scheme name,isin,units,avg nav\n"
        "Parag Parikh Flexi Cap,INF879O01019,120.5,62.4\n"
    )
    holdings = parse_portfolio_file(csv)
    assert len(holdings) == 1
    assert holdings[0].asset_type == "mutual_fund"
    assert holdings[0].symbol == "INF879O01019"


def test_mf_without_isin_or_mapping_fails_loud(tmp_path):
    csv = tmp_path / "mf_bad.csv"
    csv.write_text(
        "scheme name,units,avg nav\n"
        "Totally Made-Up Scheme Direct Growth,100,50\n"
    )
    with pytest.raises(UnmappedSymbolError):
        parse_portfolio_file(csv)


def test_empty_file_fails_loud(tmp_path):
    csv = tmp_path / "empty.csv"
    csv.write_text("name,quantity,avg_cost\n")
    with pytest.raises(ValueError):
        parse_portfolio_file(csv)
