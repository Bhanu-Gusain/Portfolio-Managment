# Portfolio Dashboard — Lean Viewer (DB-less, Ollama-less)

**Date:** 2026-04-18
**Status:** Approved for implementation
**Supersedes:** v0.2.0 architecture (SQLite + Ollama + scoring engines)

## Goal

Rebuild the portfolio app as a local, file-driven, read-only **dashboard** focused
on **data visibility and data visualisation**. Strip out SQLite, the FastAPI
backend, Ollama AI, and the scoring/technical/action engines. The user drops
portfolio CSV/XLSX files into a `portfolio_data/` folder; the dashboard reads
them, pulls live prices from yfinance + AMFI, and renders 7 tabs of
visualisations.

## Non-goals

- No database. No server process.
- No per-stock scoring, no BUY/SELL action signals, no LLM narratives.
- No broker API integration. No cloud.
- No manual DB migration. We're doing a clean break, not a migration.

## Input folder layout

```
portfolio_data/                          ← user drops files here (git-ignored)
├── stock_holdings.csv                   ← current stock positions
├── mf_holdings.csv                      ← current MF positions
├── stock_transactions.csv               ← buy/sell ledger
├── mf_transactions.csv                  ← MF purchase/redemption ledger
├── dividends.csv                        ← dividend + corporate-action log
├── watchlist.csv                        ← tickers to track (no position)
├── raw/                                 ← optional broker exports (auto-detected)
│   ├── groww_equity_*.xlsx
│   ├── zerodha_tradebook_*.csv
│   └── kuvera_mf_*.csv
└── .cache/                              ← price cache (auto-managed)
    ├── yfinance_YYYY-MM-DD.parquet
    └── amfi_YYYY-MM-DD.parquet
```

`portfolio_data/templates/` is committed to git — empty canonical CSVs with
headers the user can copy.

## Canonical file schemas

| File | Required columns |
|---|---|
| `stock_holdings.csv` | `symbol, exchange, quantity, avg_cost, currency` |
| `mf_holdings.csv` | `isin, scheme_name, units, avg_nav` |
| `stock_transactions.csv` | `date, symbol, exchange, side, quantity, price, charges, notes` |
| `mf_transactions.csv` | `date, isin, scheme_name, side, units, nav, amount, folio, notes` |
| `dividends.csv` | `date, symbol_or_isin, asset_type, amount, per_unit, notes` |
| `watchlist.csv` | `symbol_or_isin, asset_type, note` |

`side` ∈ {`buy`, `sell`}. `asset_type` ∈ {`stock`, `mutual_fund`}. Dates in
ISO-8601 (`YYYY-MM-DD`).

## Broker adapters

Files in `portfolio_data/raw/` are recognised by filename pattern + column
fingerprint:

- `groww_equity_*` → stock_holdings
- `groww_mf_*` → mf_holdings
- `zerodha_console_holdings*` → stock_holdings
- `zerodha_tradebook*` → stock_transactions
- `kuvera_*_holdings*` → mf_holdings
- `kuvera_*_transactions*` → mf_transactions

Adapters live in `services/adapters/<name>.py`, each exposing
`matches(path) -> bool` and `parse(path) -> pd.DataFrame` returning canonical
schema. Unrecognised file → loud error explaining how to fix.

## Module layout

```
analysis/
├── portfolio_data/                  ← runtime input + cache (git-ignored)
├── core/
│   ├── portfolio_engine.py          ← KEEP, rewire to DataFrames
│   ├── risk_engine.py               ← KEEP, rewire to DataFrames
│   ├── allocation_engine.py         ← KEEP, rewire to DataFrames
│   └── performance_engine.py        ← NEW: XIRR, timeseries reconstruction
├── services/
│   ├── portfolio_data_loader.py     ← NEW: reads portfolio_data/
│   ├── price_fetcher.py             ← NEW: yfinance + AMFI + disk cache
│   ├── fifo.py                      ← NEW: realised P&L (FIFO)
│   └── adapters/
│       ├── __init__.py              ← adapter registry
│       ├── groww.py
│       ├── zerodha.py
│       └── kuvera.py
├── data/                            ← mapping files (committed)
│   ├── symbol_map.csv               ← KEEP
│   ├── mf_map.csv                   ← KEEP
│   ├── sector_map.csv               ← NEW
│   └── marketcap_map.csv            ← NEW
├── frontend/
│   └── dashboard.py                 ← REWRITE: 7 tabs
├── scripts/
│   └── init_portfolio_data.py       ← NEW: creates portfolio_data/ + templates
├── utils/                           ← KEEP unchanged
└── tests/                           ← REWRITE
```

### Deletions

- `db/` (whole directory)
- `backend/` (whole directory)
- `core/ai_engine.py`, `core/scoring_engine.py`, `core/technical_engine.py`,
  `core/action_engine.py`
- `data_layer/cache.py` (SQLite-backed cache)
- `services/pipeline.py`, `services/csv_parser.py`, `services/portfolio_loader.py`
- `scripts/setup.py`, `scripts/run_daily_batch.py` (if exists)
- Tests for deleted modules

## Data flow

```
portfolio_data/*.csv,*.xlsx      portfolio_data/raw/*
         │                              │
         ▼                              ▼
   canonical loader              adapter registry
         └───────────┬──────────────────┘
                     ▼
         portfolio_data_loader.load()
                     │
                     ▼
    PortfolioData (dataclass):
      .stock_holdings, .mf_holdings,
      .stock_txns, .mf_txns,
      .dividends, .watchlist
                     │
                     ▼
         price_fetcher.enrich()
           ─── yfinance (batch) ───► stock LTP + 3mo history + NIFTY
           ─── AMFI NAV TXT ───► MF LTP
           ─── mfapi.in ───► MF historical NAV (performance tab only)
                     │
                     ▼
      analytics (portfolio/risk/allocation/performance engines)
                     │
                     ▼
       Streamlit dashboard tabs (in-memory)
```

## Pricing layer

- **`price_fetcher.fetch_stock_prices(symbols, exchange_map) -> pd.DataFrame`**:
  one `yfinance.download(tickers, period="3mo")` batch. Cached to
  `portfolio_data/.cache/yfinance_<today>.parquet`. Exchange suffixing: NSE →
  `.NS`, BSE → `.BO`.
- **`price_fetcher.fetch_mf_navs(isins) -> pd.DataFrame`**: one HTTP GET to
  `https://www.amfiindia.com/spages/NAVAll.txt`, parsed to
  `{isin: (nav, scheme_name, category)}`. Cached to
  `portfolio_data/.cache/amfi_<today>.parquet`.
- **`price_fetcher.fetch_mf_history(scheme_codes) -> dict[str, pd.DataFrame]`**:
  one HTTP GET per scheme to `https://api.mfapi.in/mf/<code>`. Used only by
  Performance tab. Cached per scheme per day.
- **Cache policy**: same-day cache hit → return cached. Older → refetch. Offline
  fetch failure → log warning, return empty frame; dashboard shows LTP as `—`
  and disables P&L columns rather than crashing.
- **Refresh button** in sidebar force-deletes today's cache files.

## Dashboard tabs

### 1. Overview
KPI row (Value / Invested / Unrealised P&L / Realised P&L YTD / Today's
change), asset-class donut, top-5 gainers/losers bar, sparkline of portfolio
value (if transactions present).

### 2. Holdings
Unified stock+MF table (type filter + search). Columns: name, type, qty,
avg_cost, LTP, invested, current, pnl, pnl_pct, weight. Treemap toggle (area =
current value, colour = P&L %).

### 3. Transactions
Combined buy/sell ledger (date/symbol/side filters). FIFO realised-P&L panel
grouped by Indian FY (Apr–Mar). Monthly buy/sell bar chart.

### 4. Performance
Portfolio value timeseries (reconstructed from transactions + historical
prices). XIRR (whole, stocks-only, MF-only) via Brent's method. NIFTY overlay.

### 5. Allocation & Risk
Sector pie (via `data/sector_map.csv`), market-cap pie (via
`data/marketcap_map.csv`), MF category pie (via AMFI category). Risk warnings
list: single-name > 12%, single-sector > 25%, holdings > 18, cash drag > 15%
(uses `risk_engine` rewired to DataFrames).

### 6. Dividends
Monthly bar, per-ticker table with yield-on-cost, FY totals.

### 7. Watchlist
Table: symbol, type, LTP, day-change %, 52w high/low, % from 52w high/low.
Input to append to `watchlist.csv`.

### Empty-state rule
Each tab declares required files. Missing file → tab renders the message
*"📄 This tab needs `X.csv`. Drop it in `portfolio_data/` and click Reload."*
No grey "—" mystery; no crash.

## Performance tab — XIRR

```python
def xirr(cashflows: list[tuple[date, float]], guess: float = 0.1) -> float:
    """Cashflows: investments negative, redemptions + current value positive."""
    from scipy.optimize import brentq
    ...
```

`scipy` added to `requirements.txt`.

## Dependencies — final

- **Keep**: streamlit, pandas, numpy, yfinance, plotly, requests, openpyxl, xlrd, pytest
- **Add**: scipy (for XIRR), pyarrow (for parquet cache)
- **Remove**: fastapi, uvicorn, pydantic, pydantic-settings, python-multipart

## Error handling philosophy

Per user's global preference: **fail loud, no silent defaults**.

- Missing required file → tab shows clear message, everything else still renders
- Unknown broker file in `raw/` → raise `UnsupportedFileError` with fix hint
- Price fetch fails → log warning, return empty, mark columns `—` (not 0 or NaN silently)
- Mapping miss (unknown symbol / ISIN) → collected and shown in sidebar "Unmapped"
  panel with instructions to add to `symbol_map.csv` / `mf_map.csv`

## Testing

- `tests/test_portfolio_data_loader.py` — reads fixtures, handles missing files
- `tests/test_adapters/test_groww.py`, `_zerodha.py`, `_kuvera.py` — one
  fixture per adapter
- `tests/test_price_fetcher.py` — mocks yfinance + AMFI, tests cache hit/miss/offline
- `tests/test_fifo.py` — FIFO realised P&L with multi-lot buy/sell sequences
- `tests/test_performance_engine.py` — XIRR with known cashflow fixtures
- `tests/test_risk_engine.py` — kept, rewired to DataFrames

Fixtures live in `tests/fixtures/portfolio_data/` (mini canonical CSVs) and
`tests/fixtures/raw/` (mini broker exports). No real holdings.

## Migration (one-time)

There is no migration — the old SQLite DB is local per-user and contained only
derived state. The replacement workflow:

1. User runs `python scripts/init_portfolio_data.py` → creates
   `portfolio_data/` with empty templates.
2. User copies their existing holdings into the canonical files (or drops
   broker exports into `raw/`).
3. User runs `streamlit run frontend/dashboard.py`.

Old DB file at `data/analysis.db` remains untouched; user can delete it
manually.

## Changelog + security

- Append `[0.3.0]` entry to `CHANGELOG.md` describing the rewrite
- Update `README.md` with the new quickstart
- Update `SECURITY.md`: remove DB/Ollama mentions, add note that
  `portfolio_data/` is git-ignored and the only place user holdings live
- Update `.gitignore` to include `portfolio_data/` (except `templates/`)
- Update `.env.example`: remove DB_PATH, OLLAMA_*; keep AMFI_NAV_URL,
  CACHE_MAX_AGE_HOURS, LOG_LEVEL

## Build sequence

1. Docs + gitignore + env: mark the new shape first so deletions don't leave rubble
2. Add `portfolio_data/templates/`, `scripts/init_portfolio_data.py`
3. Add `services/portfolio_data_loader.py` + adapters + fixtures + tests
4. Add `services/price_fetcher.py` + tests (mocked)
5. Add `services/fifo.py` + `core/performance_engine.py` + tests
6. Rewire `core/portfolio_engine.py`, `core/risk_engine.py`,
   `core/allocation_engine.py` to consume DataFrames
7. Rewrite `frontend/dashboard.py` with 7 tabs
8. Delete old modules (`db/`, `backend/`, deleted `core/` files, old
   `services/` files)
9. Update `requirements.txt`, `README.md`, `CHANGELOG.md`, `SECURITY.md`,
   `start.sh`, `start.bat`
10. Full test pass; `streamlit run` smoke

## Success criteria

- `streamlit run frontend/dashboard.py` starts with no DB, no Ollama, and an
  empty `portfolio_data/` — dashboard renders with "drop files to start"
- With the bundled sample files in `portfolio_data/`, all 7 tabs render
- `pytest -q` passes
- `grep -r "sqlite\|ollama\|fastapi" --include="*.py"` returns zero matches
  under `core/`, `services/`, `frontend/`
