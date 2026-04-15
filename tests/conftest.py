"""Pytest fixtures: isolated SQLite DB per test, project root on sys.path."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point the settings cache at a fresh SQLite file for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    from utils import config
    config.get_settings.cache_clear()

    from db.init_db import init_db
    init_db()

    yield db_path

    config.get_settings.cache_clear()
