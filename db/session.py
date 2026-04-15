"""SQLite session management. Single context manager — no pooling needed for local-first."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from utils.config import get_settings


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or get_settings().db_abspath
    conn = _connect(path)
    try:
        yield conn
    finally:
        conn.close()
