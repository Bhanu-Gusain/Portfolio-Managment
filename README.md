# AI Investment Decision Engine (Local-First, NSE)

Production-grade, local-only quant engine for Indian stock portfolios. Deterministic scoring + risk + allocation engines, with a local LLM (Ollama) providing plain-English explanations. No cloud, no broker, no credentials.

## Architecture

```
CSV upload ─► portfolio_engine ─┐
                                 ├─► pipeline ─► scoring ─► signals ─► dashboard
yfinance ─► cache ─► technical ─┘                risk
                                                  allocation
                                                  ai_engine (explanation only)
```

- **Engines drive decisions.** AI only narrates structured output.
- **Dashboard reads from DB.** Compute happens in `services/pipeline.py`.

## Setup

```bash
cd /Users/bhanugusain/Documents/Analysis
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python db/init_db.py
```

Install Ollama separately and pull the default model:
```bash
# macOS
brew install ollama
ollama serve &
ollama pull llama3.1:8b
```

## Running

```bash
# 1. Backend API
uvicorn backend.main:app --reload

# 2. Dashboard (new terminal)
streamlit run frontend/dashboard.py

# 3. One-shot daily batch (CLI)
python scripts/run_daily_batch.py
```

Open the Streamlit dashboard → upload `data/sample_groww_holdings.csv` → click **Run Daily Batch** → explore all six tabs.

## Tests

```bash
pytest -q
```

## Extending factors

Add a class in `core/scoring_engine.py` that implements the `Factor` protocol, then append it to `DEFAULT_FACTORS`. The scoring engine is factor-pluggable — no other engine changes needed.

## Directory layout

- `backend/` — FastAPI app (thin routes)
- `core/` — Quant engines (portfolio, technical, scoring, risk, allocation, action, ai)
- `data_layer/` — yfinance client, OHLCV cache, fundamentals
- `db/` — SQLite schema, repositories
- `services/` — pipeline orchestrator, CSV parser
- `frontend/dashboard.py` — Streamlit UI
- `utils/` — config, logging, time
- `data/` — sample CSVs + SQLite DB
- `tests/` — pytest suites
- `scripts/` — CLI tools
