"""Central config loader. Reads env vars from `.env` (optional) with safe defaults.

No dependency on pydantic — keeps the install surface small.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Best-effort .env loader. No dependency on python-dotenv."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    portfolio_data_dir: Path
    cache_max_age_hours: int
    amfi_nav_url: str
    mfapi_base_url: str
    log_level: str

    @property
    def cache_dir(self) -> Path:
        return self.portfolio_data_dir / ".cache"

    @property
    def raw_dir(self) -> Path:
        return self.portfolio_data_dir / "raw"

    @property
    def templates_dir(self) -> Path:
        return self.portfolio_data_dir / "templates"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    pdd = os.environ.get("PORTFOLIO_DATA_DIR", "portfolio_data")
    pdd_path = Path(pdd)
    if not pdd_path.is_absolute():
        pdd_path = PROJECT_ROOT / pdd_path

    return Settings(
        portfolio_data_dir=pdd_path,
        cache_max_age_hours=int(os.environ.get("CACHE_MAX_AGE_HOURS", "12")),
        amfi_nav_url=os.environ.get(
            "AMFI_NAV_URL", "https://www.amfiindia.com/spages/NAVAll.txt"
        ),
        mfapi_base_url=os.environ.get("MFAPI_BASE_URL", "https://api.mfapi.in/mf"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
