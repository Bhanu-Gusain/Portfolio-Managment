"""Pytest fixtures: isolated portfolio_data folder per test, project root on sys.path."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_portfolio_data(tmp_path, monkeypatch):
    """Point the settings at a fresh portfolio_data/ for each test."""
    data_dir = tmp_path / "portfolio_data"
    data_dir.mkdir()
    (data_dir / "raw").mkdir()
    (data_dir / ".cache").mkdir()

    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(data_dir))

    from utils import config
    config.get_settings.cache_clear()

    yield data_dir

    config.get_settings.cache_clear()
