#!/usr/bin/env bash
# macOS / Linux one-click launcher. Creates venv on first run, installs deps, launches dashboard.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing/updating dependencies..."
python -m pip install --upgrade pip > /dev/null
pip install -r requirements.txt

python scripts/setup.py

echo
echo "Launching dashboard at http://localhost:8501"
streamlit run frontend/dashboard.py
