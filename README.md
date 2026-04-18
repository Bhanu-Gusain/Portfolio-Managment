# Portfolio Dashboard — file-driven, local-first

A lightweight Streamlit dashboard for visualising your Indian stock + mutual fund
portfolio. Drop your CSV/XLSX files into a folder; the app reads them, pulls
live prices from yfinance + AMFI, and renders 7 tabs of data visualisation.

> **Local-first.** No database, no server, no LLM, no broker integration, no
> credentials. Your holdings never leave your laptop. See [SECURITY.md](SECURITY.md).

## What's in the dashboard

1. **Overview** — total value, invested, unrealised + realised P&L, today's change, asset-class donut, top movers, value sparkline.
2. **Holdings** — unified stock+MF table with LTP, P&L, weight; treemap toggle.
3. **Transactions** — filterable buy/sell ledger, monthly flows, FIFO realised P&L by Indian FY.
4. **Performance** — reconstructed portfolio value timeseries with NIFTY overlay + XIRR per bucket.
5. **Allocation & Risk** — sector / market-cap / MF-category breakdowns + concentration warnings.
6. **Dividends** — monthly bar, per-ticker yield-on-cost, FY totals.
7. **Watchlist** — live prices + 52w bands for symbols you track.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate                # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_portfolio_data.py    # creates portfolio_data/ with empty templates
# Edit the CSVs under portfolio_data/ with your holdings
streamlit run frontend/dashboard.py
```

Or use the launchers:

| OS | Command |
|---|---|
| macOS / Linux | `./start.sh` |
| Windows | `start.bat` |

## The `portfolio_data/` folder

This is the **only** place your holdings live. The folder is git-ignored.

```
portfolio_data/
├── stock_holdings.csv         ← your current stock positions
├── mf_holdings.csv            ← your current MF positions
├── stock_transactions.csv     ← buy/sell ledger (optional)
├── mf_transactions.csv        ← MF purchase/redemption ledger (optional)
├── dividends.csv              ← dividend log (optional)
├── watchlist.csv              ← tickers to watch (optional)
├── raw/                       ← optional: drop broker exports here
│   ├── groww_equity_*.xlsx    ← auto-detected
│   ├── zerodha_tradebook*.csv ← auto-detected
│   └── kuvera_*.csv           ← auto-detected
└── .cache/                    ← price cache (auto-managed)
```

Every file is **optional** — tabs that need a missing file will render a
message telling you which file to add. Empty templates live at
`portfolio_data/templates/` (committed to git for copy-paste).

### Canonical file schemas

| File | Required columns |
|---|---|
| `stock_holdings.csv` | `symbol, exchange, quantity, avg_cost, currency` |
| `mf_holdings.csv` | `isin, scheme_name, units, avg_nav` |
| `stock_transactions.csv` | `date, symbol, exchange, side, quantity, price, charges, notes` |
| `mf_transactions.csv` | `date, isin, scheme_name, side, units, nav, amount, folio, notes` |
| `dividends.csv` | `date, symbol_or_isin, asset_type, amount, per_unit, notes` |
| `watchlist.csv` | `symbol_or_isin, asset_type, note` |

### Broker exports

Drop a raw broker file into `portfolio_data/raw/` and the loader will try an
adapter:

| Filename pattern | Maps to |
|---|---|
| `groww_equity_*` | `stock_holdings` |
| `groww_mf_*` | `mf_holdings` |
| `zerodha_console_holdings*` | `stock_holdings` |
| `zerodha_tradebook*` | `stock_transactions` |
| `kuvera_*_holdings*` | `mf_holdings` |
| `kuvera_*_transactions*` | `mf_transactions` |

Unrecognised files fail loudly with an actionable hint. To add a new adapter,
drop a module into `services/adapters/` that exposes `NAME`, `matches(path)`,
and `parse(path) -> DataFrame`, and add it to `ADAPTERS` in
`services/adapters/__init__.py`.

## Pricing

- **Stocks** — yfinance, batched per session. Append `.NS` for NSE or `.BO`
  for BSE in your `symbol` column.
- **Mutual funds** — [AMFI India](https://www.amfiindia.com/spages/NAVAll.txt)
  NAV feed, keyed by ISIN. Category metadata powers the MF-category pie.
- **MF historical NAV** — [api.mfapi.in](https://api.mfapi.in) by AMFI scheme
  code (only used by the Performance tab).
- **Cache** — parquet files in `portfolio_data/.cache/`. Same-day hit → served
  from disk; stale → refetched. "🔄 Refresh prices" in the sidebar nukes today's
  cache.

If a fetch fails or you're offline, LTP columns show `—` and the rest of the
dashboard still works on cost-basis numbers.

## Directory layout

| Path | Purpose |
|---|---|
| `portfolio_data/` | Your portfolio files (git-ignored, user-local) |
| `core/` | Pure-Python engines: `portfolio_engine`, `risk_engine`, `allocation_engine`, `performance_engine` (XIRR) |
| `services/` | `portfolio_data_loader`, `price_fetcher`, `fifo`, `adapters/` |
| `frontend/dashboard.py` | Streamlit UI (7 tabs) |
| `data/` | Reference maps (symbol, sector, market-cap, MF) — committed |
| `scripts/init_portfolio_data.py` | One-time scaffold script |
| `tests/` | pytest suite |
| `utils/` | Config loader, logging |

## Tests

```bash
pytest -q
```

The test suite mocks yfinance and AMFI — no network access required.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Security & privacy

See [SECURITY.md](SECURITY.md). TL;DR: no personal data in code, the only
outbound calls are yfinance / AMFI / api.mfapi.in (all public, unauthenticated,
read-only), no credentials ever committed.

## Licence

MIT — add a LICENSE file before publishing.
