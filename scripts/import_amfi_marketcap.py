"""One-shot importer that overwrites `data/marketcap_map.csv` from an AMFI
"Categorization of Stocks" Excel file.

AMFI publishes this list every six months (Jan + Jul) at:
    https://www.amfiindia.com/research-information/other-data/categorization-of-stocks

Usage:
    python scripts/import_amfi_marketcap.py path/to/AMFI_categorization.xlsx

Behaviour:
    - Detects sheets whose name contains "Large", "Mid", or "Small" (case-insensitive).
    - Auto-locates the row that looks like a header (must contain a Symbol-like column).
    - Auto-detects the symbol column (`Symbol`, `NSE Symbol`, `Ticker`, etc.).
    - Writes the new map to `data/marketcap_map.csv`, preserving any existing
      `ETF` rows (AMFI doesn't classify ETFs).
    - Prints a diff summary so you can sanity-check before/after.

Nothing leaves your machine — the file is read locally, parsed locally,
written locally.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "data" / "marketcap_map.csv"

BUCKET_KEYWORDS = {
    "Large": ("large",),
    "Mid": ("mid",),
    "Small": ("small",),
}

SYMBOL_COL_CANDIDATES = (
    "symbol", "nse symbol", "ticker", "trading symbol", "scrip", "scrip code",
)


def _find_header_row(raw: pd.DataFrame) -> int | None:
    for idx, row in raw.iterrows():
        cells = [str(v).strip().lower() for v in row.tolist()]
        if any(c in SYMBOL_COL_CANDIDATES for c in cells):
            return int(idx)
    return None


def _extract_symbols(path: Path, sheet: str) -> list[str]:
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")
    header = _find_header_row(raw)
    if header is None:
        return []
    df = pd.read_excel(path, sheet_name=sheet, header=header, engine="openpyxl")
    df.columns = [str(c).strip().lower() for c in df.columns]
    sym_col = next((c for c in df.columns if c in SYMBOL_COL_CANDIDATES), None)
    if not sym_col:
        return []
    syms = (df[sym_col].dropna().astype(str).str.strip().str.upper())
    return [s for s in syms if s and not s.startswith("UNNAMED")]


def import_amfi(xlsx: Path) -> dict[str, str]:
    """Return {symbol: bucket} for buckets present in the workbook."""
    xl = pd.ExcelFile(xlsx, engine="openpyxl")
    mapping: dict[str, str] = {}

    for bucket, keywords in BUCKET_KEYWORDS.items():
        match = next((s for s in xl.sheet_names
                      if any(k in s.lower() for k in keywords)), None)
        if not match:
            print(f"  ⚠  no sheet matched {bucket!r} keywords — skipping")
            continue
        symbols = _extract_symbols(xlsx, match)
        for s in symbols:
            mapping[s] = bucket
        print(f"  ✓ {bucket}: {len(symbols)} symbols from sheet {match!r}")
    return mapping


def merge_with_existing(new_map: dict[str, str]) -> pd.DataFrame:
    """Preserve manual ETF rows; AMFI overwrites Large/Mid/Small."""
    rows = [{"symbol": k, "market_cap": v} for k, v in sorted(new_map.items())]
    if MAP_PATH.exists():
        old = pd.read_csv(MAP_PATH)
        old["symbol"] = old["symbol"].astype(str).str.strip().str.upper()
        etfs = old[old["market_cap"].str.upper() == "ETF"]
        rows += [
            {"symbol": s, "market_cap": "ETF"}
            for s in etfs["symbol"].tolist()
            if s not in new_map
        ]
    return pd.DataFrame(rows).drop_duplicates(subset=["symbol"]).sort_values("symbol")


def diff_summary(old_path: Path, new_df: pd.DataFrame) -> None:
    if not old_path.exists():
        print(f"\n  (no existing {old_path.name} — full overwrite)")
        return
    old = pd.read_csv(old_path)
    old["symbol"] = old["symbol"].str.upper()
    old_map = dict(zip(old["symbol"], old["market_cap"]))
    new_map = dict(zip(new_df["symbol"], new_df["market_cap"]))

    added = sorted(set(new_map) - set(old_map))
    removed = sorted(set(old_map) - set(new_map))
    changed = sorted(s for s in set(old_map) & set(new_map) if old_map[s] != new_map[s])

    print(f"\n  Diff: +{len(added)} added, -{len(removed)} removed, ~{len(changed)} reclassified")
    for s in changed[:20]:
        print(f"    ~ {s}: {old_map[s]} → {new_map[s]}")
    if len(changed) > 20:
        print(f"    … and {len(changed) - 20} more")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    xlsx = Path(sys.argv[1]).expanduser().resolve()
    if not xlsx.exists():
        print(f"❌ File not found: {xlsx}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {xlsx.name}…")
    mapping = import_amfi(xlsx)
    if not mapping:
        print("❌ No symbols extracted — file format unrecognised.", file=sys.stderr)
        sys.exit(1)

    new_df = merge_with_existing(mapping)
    diff_summary(MAP_PATH, new_df)

    new_df.to_csv(MAP_PATH, index=False)
    print(f"\n✅ Wrote {len(new_df)} rows to {MAP_PATH.relative_to(ROOT)}")
    print("   Refresh the dashboard (press R or Clear cache) to see updated buckets.")


if __name__ == "__main__":
    main()
