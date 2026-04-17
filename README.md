# Portfolio Management — Local-First Quant Engine

Plug-and-play desktop dashboard for Indian retail portfolios. Upload a CSV or Excel
file of your **stocks or mutual funds**, and get deterministic scoring, risk warnings,
rebalance suggestions, and daily action signals — all computed **locally** on your
machine. No cloud, no broker integration, no credentials.

> **Privacy first.** Your holdings never leave your laptop. See [SECURITY.md](SECURITY.md).

## Features

- **Upload any layout** — CSV, XLSX, or XLS. Auto-detects columns from Groww,
  Zerodha, Kuvera, or a hand-typed spreadsheet.
- **Stocks + mutual funds** in one portfolio. Stocks priced via Yahoo Finance,
  mutual funds priced via AMFI India's public NAV feed.
- **Factor-based scoring** (0–10 scale) with 6 pluggable factors.
- **Risk engine** flags concentration, bloat, and under/overweight positions.
- **Daily actions** — SELL / ADD / WATCH signals from score + trend confluence.
- **Optional AI narratives** via local Ollama. If Ollama isn't installed, the rest
  of the app still works — AI tab just shows "unavailable".
- **Full audit log** — every upload, pipeline run, and change is recorded in
  `CHANGELOG.md` automatically.

## Quickstart (zero config)

### Windows
Double-click `start.bat`. It creates a virtualenv, installs dependencies, initialises
the database, and opens the dashboard at http://localhost:8501.

### macOS / Linux
```bash
./start.sh
```

### Manual setup (any OS)
```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup.py
streamlit run frontend/dashboard.py
```

## Using the app

1. Open the dashboard.
2. In the sidebar, upload a portfolio file. A sample is included at
   `data/sample_holdings.csv` — mixed stocks + mutual funds.
3. Click **Run Daily Batch**. Prices are pulled (~30s), indicators computed,
   factors scored, snapshot written.
4. Explore the 6 tabs: Overview, Holdings, Scoring, Risk, Actions, AI Insights.

## Supported upload formats

The loader auto-detects layout. Any of these work:

| Layout | Columns |
|---|---|
| **Unified (recommended)** | `asset_type, name, identifier, quantity, avg_cost` |
| Groww equity export | `Stock Name, ISIN, Quantity, Average buy price, …` |
| Mutual fund export | `Scheme Name, ISIN, Units, NAV` or `Scheme Name, Units, Avg NAV` |
| Hand-typed | Minimum: name/symbol + quantity + avg cost |

If a stock name is unknown, the app tells you to add it to `data/symbol_map.csv`.
Mutual funds need either an ISIN in the upload, or an entry in `data/mf_map.csv`.

## Optional: enable AI narratives

Install [Ollama](https://ollama.com), then:

```bash
ollama serve &
ollama pull llama3.1:8b
```

The AI Insights tab activates automatically. Ollama runs **locally** — no data
leaves your machine.

## Architecture

```
CSV/XLSX upload ─► portfolio_loader ─► holdings_repo ──┐
                                                        │
yfinance (stocks) ─┐                                    ▼
AMFI (MF NAVs)     ├─► cache ─► pipeline ─► scoring ──► dashboard
                   │                        risk
                   └──────────────────────► actions
                                            ai_engine (explanations only)
```

- **Engines decide.** AI never picks trades.
- **Dashboard reads.** Compute happens only in `services/pipeline.py`.

## Directory layout

| Path | What |
|---|---|
| `backend/` | FastAPI app (thin routes) — optional; the dashboard works without it |
| `core/` | Portfolio, technical, scoring, risk, allocation, action, AI engines |
| `data_layer/` | yfinance, AMFI, cache, fundamentals |
| `db/` | SQLite schema + repositories + audit log |
| `services/` | Pipeline orchestrator + unified portfolio loader |
| `frontend/dashboard.py` | Streamlit UI |
| `scripts/` | Setup + CLI daily batch |
| `tests/` | pytest suite |
| `data/` | Sample CSVs, symbol maps, local SQLite DB (git-ignored) |

## Tests

```bash
pytest -q
```

## Extending factors

Add a class in `core/scoring_engine.py` implementing the `Factor` protocol, then
append to `DEFAULT_FACTORS`. The scoring engine is factor-pluggable — no other
engine changes needed.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and runtime event log.

## Security & privacy

See [SECURITY.md](SECURITY.md). TL;DR: no personal data in code, no outbound calls
other than public-API price lookups, no credentials ever committed.

## Licence

MIT — see `LICENSE` file (add one before forking if you plan to redistribute).
