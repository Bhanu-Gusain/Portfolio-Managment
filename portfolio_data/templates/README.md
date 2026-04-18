# Portfolio Data Templates

Copy any of these files one directory up (to `portfolio_data/`) and fill in
your own holdings / transactions / dividends / watchlist. The dashboard reads
those, not these. Each file is optional — tabs that need data from a missing
file will tell you which file to add.

Do **not** edit files in this folder for your own holdings; they're committed
to git. Your copies (in `portfolio_data/` alongside this folder) are
git-ignored.

## Files

| File | Purpose | Required columns |
|---|---|---|
| `stock_holdings.csv` | Current stock positions | `symbol, exchange, quantity, avg_cost, currency` |
| `mf_holdings.csv` | Current mutual fund positions | `isin, scheme_name, units, avg_nav` |
| `stock_transactions.csv` | Buy/sell ledger | `date, symbol, exchange, side, quantity, price, charges, notes` |
| `mf_transactions.csv` | MF purchase/redemption ledger | `date, isin, scheme_name, side, units, nav, amount, folio, notes` |
| `dividends.csv` | Dividend + corporate-action log | `date, symbol_or_isin, asset_type, amount, per_unit, notes` |
| `watchlist.csv` | Tickers to track (no position) | `symbol_or_isin, asset_type, note` |

## Field conventions

- `date` — ISO-8601 (`YYYY-MM-DD`)
- `side` — `buy` or `sell`
- `asset_type` — `stock` or `mutual_fund`
- `exchange` — `NSE` or `BSE`
- `currency` — `INR` (USD etc supported but not FX-converted)

## Broker exports

Drop raw broker exports (Groww, Zerodha, Kuvera) into `portfolio_data/raw/`.
They're auto-detected by filename pattern — see the project README.
