"""CLI: run the daily batch pipeline. Usage: python scripts/run_daily_batch.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.init_db import init_db  # noqa: E402
from services.pipeline import run_daily_batch  # noqa: E402
from utils.logging import get_logger  # noqa: E402


def main() -> int:
    log = get_logger("daily_batch")
    init_db()
    try:
        snap_id = run_daily_batch()
    except RuntimeError as exc:
        log.error("Pipeline failed: %s", exc)
        return 1
    log.info("Wrote snapshot %d", snap_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
