#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "========================================"
echo "  N.E.H.A — Multi-agent org desk"
echo "========================================"
echo "Set OPENAI_API_KEY in .env for live tool calling."
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[dev]"
[[ -f .env ]] || cp .env.example .env
mkdir -p workspace
echo "Serving http://127.0.0.1:8000"
exec python -m grok_org_os.cli serve --host 127.0.0.1 --port 8000
