#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import bleak' 2>/dev/null; then
  .venv/bin/python -m pip install -r requirements.txt
fi
if [[ -x node_modules/.bin/portless ]]; then
  bash scripts/name.sh
fi
exec .venv/bin/python scripts/server.py "$@"
