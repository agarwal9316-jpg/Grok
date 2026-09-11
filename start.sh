#!/usr/bin/env bash
# Grok Org OS — Mac/Linux portable launcher
set -euo pipefail
cd "$(dirname "$0")"

echo "========================================"
echo "  Grok Org OS — portable desk GUI"
echo "========================================"
echo "This folder is the portable app — copy it anywhere."
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3.11+."
  exit 1
fi

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || {
  echo "ERROR: Python 3.11+ required"
  exit 1
}

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment .venv ..."
  python3 -m venv .venv
fi

echo "Installing / updating dependencies ..."
.venv/bin/python -m pip install --upgrade pip >/dev/null
if ! .venv/bin/python -m pip install -e ".[dev,desktop]"; then
  .venv/bin/python -m pip install -e ".[dev]"
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
fi

URL="http://127.0.0.1:8000"
echo ""
echo "Starting API + GUI at $URL"
echo "  Docs: ${URL}/docs"

if .venv/bin/python -c "import webview" >/dev/null 2>&1; then
  exec .venv/bin/python -m grok_org_os.cli desktop --host 127.0.0.1 --port 8000
fi

if command -v xdg-open >/dev/null 2>&1; then
  (sleep 1.5 && xdg-open "$URL") >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
  (sleep 1.5 && open "$URL") >/dev/null 2>&1 &
fi

exec .venv/bin/python -m uvicorn grok_org_os.api.app:app --host 127.0.0.1 --port 8000
