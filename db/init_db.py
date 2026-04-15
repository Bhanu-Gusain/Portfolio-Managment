"""Initialize the SQLite database from schema.sql. Idempotent."""
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


def init_db() -> Path:
    settings = get_settings()
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(sql)
    log.info("Database initialised at %s", settings.db_abspath)
    return settings.db_abspath


if __name__ == "__main__":
    init_db()
