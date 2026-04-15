PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stocks_master (
  symbol TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  sector TEXT,
  industry TEXT,
  added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_data (
  symbol TEXT NOT NULL,
  date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume INTEGER,
  PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_price_symbol_date ON price_data(symbol, date DESC);

CREATE TABLE IF NOT EXISTS technical_indicators (
  symbol TEXT NOT NULL,
  date TEXT NOT NULL,
  ema21 REAL,
  ema50 REAL,
  ema200 REAL,
  rsi14 REAL,
  macd REAL,
  macd_signal REAL,
  macd_hist REAL,
  high_52w REAL,
  low_52w REAL,
  trend_label TEXT,
  is_breakout INTEGER,
  PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
  symbol TEXT PRIMARY KEY,
  roe REAL,
  sales_growth_3y REAL,
  debt_to_equity REAL,
  pe REAL,
  market_cap REAL,
  source TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_holdings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  quantity REAL NOT NULL,
  avg_cost REAL NOT NULL,
  uploaded_at TEXT NOT NULL,
  FOREIGN KEY (symbol) REFERENCES stocks_master(symbol)
);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol ON portfolio_holdings(symbol);

CREATE TABLE IF NOT EXISTS scores (
  symbol TEXT NOT NULL,
  date TEXT NOT NULL,
  score REAL NOT NULL,
  label TEXT NOT NULL,
  factor_breakdown TEXT NOT NULL,
  PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  action TEXT NOT NULL,
  reason TEXT NOT NULL,
  score REAL,
  trend_label TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date DESC);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  taken_at TEXT NOT NULL,
  total_value REAL,
  total_pnl REAL,
  portfolio_score REAL,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_taken_at ON snapshots(taken_at DESC);
