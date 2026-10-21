#!/usr/bin/env bash
# Non-interactive setup: dependencies -> schema -> demo seed. Never starts the server.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Installing Python dependencies (project-level only)"
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt

echo "==> Creating the SQLite schema and seeding the demo club"
python3 -m app.seed

echo "==> Checking the application imports cleanly"
python3 -c "import app.main"

echo
echo "Setup complete."
echo "Start the server with:"
echo '  python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"'
