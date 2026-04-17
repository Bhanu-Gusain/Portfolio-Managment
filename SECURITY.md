# Security & Privacy

This project is **local-first**. Nothing in the codebase collects, transmits, or persists your personal data to any remote service.

## What is stored where

| Data | Location | Ever leaves your machine? |
|---|---|---|
| Your holdings (symbol, qty, cost) | `data/analysis.db` (SQLite, local) | **No** |
| Uploaded CSV/Excel files | `data/uploads/` (local, git-ignored) | **No** |
| Price data (OHLCV cache) | `data/analysis.db` (local) | **No** |
| Fundamentals | `data/analysis.db` (local) | **No** |
| AI explanations | In-memory, rendered in the dashboard | **No** (LLM runs locally via Ollama) |

## What this repo must NEVER contain

- Real brokerage account numbers, PAN, mobile numbers, email addresses, names.
- API keys, broker tokens, OAuth secrets, session cookies.
- Real portfolio CSV/Excel files. The only sample file checked in is `data/sample_holdings.csv` (hand-crafted, public NSE tickers only).
- Any file matching patterns in `.gitignore` under "User uploads".

If you ever paste real portfolio data into a file tracked by git, run:

```bash
git rm --cached <file>
git commit -m "remove accidentally tracked personal data"
```

…and rotate any credentials that may have been exposed.

## External network calls (all read-only, all public APIs, no auth)

| Service | Purpose | Data sent |
|---|---|---|
| Yahoo Finance (`yfinance`) | Historical prices + basic info | Public tickers only |
| AMFI India (`amfiindia.com`) | Mutual fund NAVs | None — downloads a public text file |
| Ollama (`localhost:11434`) | AI narratives (optional) | Portfolio aggregates, **never** your name or account details |

There are **no** outbound calls to:
- Your broker
- Anthropic / OpenAI / any cloud LLM
- Any analytics, telemetry, or crash-reporting service

## Hardening checklist (for forks / contributors)

- [ ] `.env` is in `.gitignore` — verify `git check-ignore .env` prints `.env`.
- [ ] No personal identifiers in sample data — `data/*.csv` files are generic.
- [ ] `data/analysis.db` is git-ignored.
- [ ] Uploads directory is git-ignored.
- [ ] Before pushing a PR: run `git ls-files | xargs grep -l -i -E '(pan|aadhaar|mobile|@gmail|@yahoo|@outlook)'` and confirm no hits.

## Reporting a vulnerability

Open a private GitHub security advisory on this repository. Do not file a public issue for security reports.
