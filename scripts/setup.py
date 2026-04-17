"""One-shot setup: create venv-agnostic defaults, init DB, seed .env. Cross-platform.

Run after `pip install -r requirements.txt`:

    python scripts/setup.py

Idempotent — safe to re-run.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_env() -> None:
    env = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env.exists() and example.exists():
        shutil.copy(example, env)
        print(f"Created {env.relative_to(ROOT)} from .env.example")
    else:
        print(".env already present — leaving untouched.")


def _ensure_dirs() -> None:
    (ROOT / "data" / "uploads").mkdir(parents=True, exist_ok=True)
    print("Ensured data/ and data/uploads/")


def _init_db() -> None:
    from db.init_db import init_db
    path = init_db()
    print(f"Database ready at {path}")


def main() -> None:
    print("Portfolio Management — setup")
    print("=" * 40)
    _ensure_env()
    _ensure_dirs()
    _init_db()
    print()
    print("Setup complete. Start the dashboard with:")
    print("    streamlit run frontend/dashboard.py")


if __name__ == "__main__":
    main()
