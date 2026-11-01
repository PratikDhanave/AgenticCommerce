#!/usr/bin/env bash
# One process serves the API and the built UI. Open http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"
[ -d web/dist ] || (cd web && npm install --silent && npm run build)
exec .venv/bin/uvicorn agents.server:app --host 127.0.0.1 --port "${PORT:-8000}"
