# Security & Privacy

This project is **local-first**. Nothing in the codebase collects, transmits, or persists your personal data to any remote service.

## What is stored where

| Data | Location | Git-tracked? |
|---|---|---|
| Your stocks / MFs / transactions / dividends | `portfolio_data/*.csv` | **No** (git-ignored) |
| Raw broker exports | `portfolio_data/raw/*` | **No** (git-ignored) |
| Price cache (parquet) | `portfolio_data/.cache/*` | **No** (git-ignored) |
| Canonical CSV templates (empty headers) | `portfolio_data/templates/*` | Yes — no data |
| Symbol / sector / market-cap maps | `data/*.csv` | Yes — public reference only |
| Source code | everywhere else | Yes |

## External network calls (all read-only, all public APIs, no auth)

| Service | Purpose | Data sent |
|---|---|---|
| Yahoo Finance (`yfinance`) | Stock LTP + history + 52w bands | Public tickers only |
| AMFI India (`amfiindia.com/spages/NAVAll.txt`) | MF NAVs + category metadata | None — GET a public text file |
| `api.mfapi.in` | MF historical NAV (Performance tab only) | Scheme code only |

There are **no** outbound calls to:
- Your broker
- Anthropic / OpenAI / any cloud LLM
- Any analytics, telemetry, or crash-reporting service

The only data that ever leaves your machine is **stock tickers and MF scheme
codes** — never positions, quantities, buy prices, or personal identifiers.

## What this repo must NEVER contain

- Real brokerage account numbers, PAN, mobile numbers, email addresses, names.
- API keys, broker tokens, OAuth secrets, session cookies.
- Real portfolio CSV/Excel files. The only sample data shipped is in
  `data/symbol_map.csv`, `data/sector_map.csv`, `data/marketcap_map.csv`,
  `data/mf_map.csv` (all public tickers / ISINs, no personal data).
- Any file matching patterns in `.gitignore` under `portfolio_data/`.

If you ever paste real portfolio data into a git-tracked file:

```bash
git rm --cached <file>
git commit -m "remove accidentally tracked personal data"
```

## Hardening checklist (forks / contributors)

- [ ] `git check-ignore portfolio_data/stock_holdings.csv` prints the path (= ignored)
- [ ] `grep -r "your-name\|email\|pan\|aadhaar" --include="*.csv" data/` returns nothing
- [ ] `.env` is git-ignored (`.env.example` is fine to commit)
- [ ] Before pushing a PR: run `git ls-files | xargs grep -l -i -E '(pan|aadhaar|mobile|@gmail|@yahoo|@outlook)'` and confirm no hits.

## Network-free mode

For zero-network operation:
- Pre-populate `portfolio_data/.cache/` with parquet snapshots from an online run.
- Do not click "Refresh prices" in the sidebar.
- The dashboard works fully on cost-basis data without any fetch.

## Reporting a vulnerability

Open a private GitHub security advisory on this repository. Do not file a
public issue for security reports.
