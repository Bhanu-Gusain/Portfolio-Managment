"""Initialize the SQLite database from schema.sql. Idempotent + migrates old DBs."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script from project root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.session import get_conn  # noqa: E402
from utils.config import get_settings  # noqa: E402
from utils.logging import get_logger  # noqa: E402

log = get_logger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _migrate(conn) -> None:
    """Add columns introduced after v0.1.0. Safe on fresh DBs too (columns will already exist)."""
    for table in ("portfolio_holdings", "stocks_master"):
        try:
            cols = _column_names(conn, table)
        except Exception:
            continue
        if cols and "asset_type" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN asset_type TEXT NOT NULL DEFAULT 'stock'")
            log.info("Migrated: added asset_type to %s", table)


def init_db() -> Path:
    settings = get_settings()
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(sql)
        _migrate(conn)
    log.info("Database initialised at %s", settings.db_abspath)
    return settings.db_abspath


if __name__ == "__main__":
    init_db()
