# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions use
[SemVer](https://semver.org/spec/v2.0.0.html).

**Contributor note:** every PR must append a bullet under `[Unreleased]`. The
running app also appends runtime events (uploads, pipeline runs) to the
"Runtime events" section at the bottom of this file automatically.

---

## [Unreleased]

## [0.3.0] — 2026-04-18

### Changed — full rewrite
- **No more database.** SQLite is gone. The app is now a pure file-driven,
  in-memory read-only dashboard. Delete `data/analysis.db*` at your leisure
  — it's no longer used.
- **No more Ollama / LLM.** AI narratives, scoring, and action engines removed.
  If you want them back, `git revert` 0.2.0 → 0.3.0.
- **No more FastAPI backend.** Streamlit is the entire app.
- **New `portfolio_data/` folder.** Your holdings, transactions, dividends and
  watchlist now live as plain CSV files here (git-ignored). Templates shipped
  in `portfolio_data/templates/`. Run `python scripts/init_portfolio_data.py`
  to scaffold.
- **Broker export adapters.** Drop Groww/Zerodha/Kuvera exports into
  `portfolio_data/raw/` — they're auto-detected by filename + schema.

### Added
- 7-tab Streamlit dashboard: Overview, Holdings, Transactions, Performance,
  Allocation & Risk, Dividends, Watchlist.
- `services/portfolio_data_loader.py` — loads and validates all canonical
  files with per-field coercion (numeric, date, side normalisation, ISIN
  upper-casing).
- `services/price_fetcher.py` — yfinance + AMFI + mfapi.in with
  same-day parquet cache in `portfolio_data/.cache/` and a one-click
  "Refresh prices" button.
- `services/fifo.py` — FIFO realised-P&L from transaction ledgers, with
  per-lot charge allocation and Indian FY (`FYnn-nn`) labels.
- `core/performance_engine.py` — XIRR (Brent's method) + daily portfolio
  value timeseries reconstructed from transactions + historical prices.
- `data/sector_map.csv`, `data/marketcap_map.csv` — stock classification
  maps powering the Allocation & Risk pies.
- Empty-state behaviour per tab — missing files show an explanatory message
  instead of crashing or mysteriously blank panels.

### Removed
- `db/` (all repositories, schema, audit log)
- `backend/` (FastAPI routes)
- `core/ai_engine.py`, `core/scoring_engine.py`, `core/technical_engine.py`,
  `core/action_engine.py`
- `data_layer/` (yfinance_client, amfi_client, cache, fundamentals — the
  public-facing equivalents live in `price_fetcher.py` now)
- `services/pipeline.py`, `services/csv_parser.py`, `services/portfolio_loader.py`
- `scripts/setup.py`, `scripts/run_daily_batch.py`
- Dependencies: fastapi, uvicorn, pydantic, pydantic-settings, python-multipart

### Dependencies
- Added: `scipy` (XIRR), `pyarrow` (parquet cache)

## [0.2.0] — 2026-04-18

### Added
- **Excel upload support.** The portfolio loader now accepts `.xlsx` and `.xls`
  in addition to `.csv`. Added `openpyxl` and `xlrd` to `requirements.txt`.
- **Mutual fund holdings.** Holdings carry an `asset_type` discriminator
  (`stock` | `mutual_fund` | `etf`). NAVs are fetched from the public AMFI India
  feed (`https://www.amfiindia.com/spages/NAVAll.txt`) and cached locally.
  ISINs are used as the symbol for MFs; scheme names can be mapped via
  `data/mf_map.csv`.
- **Unified portfolio loader** (`services/portfolio_loader.py`). Auto-detects
  stock vs MF rows, tolerates many column layouts, never silently drops rows.
- **Audit log.** New `audit_log` table + `db/repositories/audit_repo.py`. Every
  data-mutating event (upload, pipeline run, holdings replacement) is recorded
  and mirrored to this CHANGELOG's "Runtime events" section.
- **Plug-and-play launchers.** `start.bat` (Windows) and `start.sh`
  (macOS/Linux) create a venv, install deps, initialise the DB, and open the
  dashboard in one step. Added `scripts/setup.py` for manual setups.
- **SECURITY.md** documenting the project's privacy guarantees and the
  hardening checklist for forks.
- **Generic sample portfolio** at `data/sample_holdings.csv` (mixed
  stocks + MFs, uses the unified format). Old Groww sample retained for
  backward-compat tests.
- **Ollama health check** (`ai_engine.is_available()`) so the UI can degrade
  gracefully when the LLM is offline.
- **New env var:** `AMFI_NAV_URL` (defaults to the public AMFI endpoint).

### Changed
- Upload route and dashboard sidebar now accept CSV/XLSX/XLS and handle mixed
  stock+MF portfolios in a single file.
- `services/csv_parser.py` is now a backward-compat shim that re-exports from
  `services/portfolio_loader.py`. Existing imports continue to work.
- `db/init_db.py` migrates pre-0.2.0 databases by adding the `asset_type`
  column to `portfolio_holdings` and `stocks_master`. No data loss.
- Pipeline skips technicals, fundamentals, and scoring for mutual funds — they
  contribute to portfolio value/allocation but not to per-stock signals.
- `compute_positions` now works uniformly for stocks and mutual funds because
  MF NAVs land in `price_data` via the same path as stock closes.

### Security
- Expanded `.gitignore` to block: all user upload patterns (`data/user_*`,
  `data/my_*`, `data/uploads/`, `data/personal_*`), every SQLite variant,
  credential file patterns (`*.pem`, `*.key`, `credentials.json`, etc.), and
  all `.env*` files except `.env.example`.
- `.env.example` now ships with safe defaults only. No credentials have ever
  been tracked in this repo.
- Documented in `SECURITY.md`: what's stored where, every external network
  call the app makes (yfinance, AMFI, optional local Ollama), and a
  pre-publish checklist.

## [0.1.0] — 2026-04-15

### Added
- Initial scaffold: `backend/`, `core/`, `data_layer/`, `db/`, `services/`,
  `utils/`, `frontend/`, `tests/`, `scripts/`, `data/`.
- SQLite schema: `stocks_master`, `price_data`, `technical_indicators`,
  `fundamentals`, `portfolio_holdings`, `scores`, `signals`, `snapshots`.
- Core engines: portfolio, technical (EMA/RSI/MACD/trend/breakout),
  scoring (pluggable factor protocol, 6 default factors, 0–10 scale),
  risk (5 warnings), allocation (MAX 18, 12%, 3% constraints),
  action (SELL/ADD/WATCH), AI (Ollama llama3.1:8b narrative wrapper).
- Data layer: yfinance batch fetcher + SQLite OHLCV cache + fundamentals
  overrides CSV merge.
- FastAPI routes: `/portfolio`, `/analysis`, `/actions`, `/ai`, `/pipeline`.
  Thin routes, business logic in core.
- Streamlit dashboard: 6 tabs (Overview, Holdings, Scoring, Risk, Actions,
  AI Insights) with Plotly charts.
- Seed data: sample Groww holdings CSV, watchlist, symbol_map,
  fundamentals_overrides.
- Pytest suites for portfolio, technical, scoring, risk, allocation,
  csv_parser engines.

---

## Runtime events

*Removed in 0.3.0 along with the audit log table. Legacy entries below are
retained for archival purposes only.*
- `2026-04-17T19:03:08.841805+00:00` **holdings_replaced** — count=2
- `2026-04-17T19:03:09.027126+00:00` **holdings_replaced** — count=1
