#!/usr/bin/env bash

set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but was not found in PATH."
  exit 1
fi

python3.10 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Error: Python 3.10+ is required.")
print(f"Using Python {sys.version.split()[0]}")
PY

if [ ! -d ".venv" ]; then
  python3.10 -m venv .venv
fi

source .venv/bin/activate

python -m pip install --upgrade pip

if [ -f "requirements.txt" ]; then
  python -m pip install -r requirements.txt
else
  python -m pip install google-adk pyyaml
fi

echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
