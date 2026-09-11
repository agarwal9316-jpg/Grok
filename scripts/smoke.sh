#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m grok_org_os.cli bootstrap
python -m grok_org_os.cli run-demo
