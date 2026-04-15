# PROJECT_CHANGELOG

## 2026-04-15 — v0.1.0 Initial scaffold

- Project structure created: backend, core, data_layer, db, services, utils, frontend, tests, scripts, data.
- Database schema: stocks_master, price_data, technical_indicators, fundamentals, portfolio_holdings, scores, signals, snapshots.
- Core engines implemented: portfolio, technical (EMA/RSI/MACD/trend/breakout), scoring (pluggable factor protocol, 6 default factors, 0–10 scale), risk (5 warnings), allocation (MAX 18, 12%, 3% constraints), action (SELL/ADD/WATCH), AI (Ollama llama3.1:8b narrative wrapper).
- Data layer: yfinance batch fetcher + SQLite OHLCV cache + fundamentals overrides CSV merge.
- FastAPI routes: /portfolio, /analysis, /actions, /ai, /pipeline. Thin routes, business logic in core.
- Streamlit dashboard: 6 tabs (Overview, Holdings, Scoring, Risk, Actions, AI Insights) with Plotly charts.
- Sample Groww holdings CSV, watchlist, symbol_map, fundamentals_overrides seeded.
- Pytest suites for portfolio, technical, scoring, risk, allocation, csv_parser engines.
