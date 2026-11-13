#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# .localhost resolves in browsers without editing the system hosts file.
export PORTLESS_SYNC_HOSTS=0
./node_modules/.bin/portless proxy start --no-tls --port 1355
./node_modules/.bin/portless alias cool-lights 8765 --upstream http://localhost:8765
