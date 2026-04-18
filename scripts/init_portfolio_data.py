"""Copy canonical CSV templates into the user's portfolio_data/ folder.

Safe to re-run — never overwrites existing files.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config import get_settings  # noqa: E402


TEMPLATE_FILES = [
    "stock_holdings.csv",
    "mf_holdings.csv",
    "stock_transactions.csv",
    "mf_transactions.csv",
    "dividends.csv",
    "watchlist.csv",
]


def init() -> None:
    settings = get_settings()
    target = settings.portfolio_data_dir
    source = settings.templates_dir

    if not source.exists():
        print(f"❌  Templates dir missing at {source}. Re-clone the repo.", file=sys.stderr)
        sys.exit(1)

    target.mkdir(parents=True, exist_ok=True)
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    for name in TEMPLATE_FILES:
        dst = target / name
        if dst.exists():
            skipped += 1
            continue
        shutil.copy2(source / name, dst)
        created += 1

    print(f"✅  Portfolio data folder ready at {target}")
    print(f"   created: {created} new file(s), skipped: {skipped} existing")
    print(f"   raw exports folder: {settings.raw_dir}")
    print(f"   price cache folder: {settings.cache_dir}")
    print()
    print("Next: edit the CSV files with your holdings, then run:")
    print("   streamlit run frontend/dashboard.py")


if __name__ == "__main__":
    init()
