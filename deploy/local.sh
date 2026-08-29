#!/usr/bin/env bash
# Run Atlas locally with ZERO Google Cloud requirements.
#   STORE_BACKEND=local → JSON-file ledger
#   GEMINI_API_KEY unset → planner falls back to a heuristic plan
# The agent still runs on the Gemini API if you export GEMINI_API_KEY.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -r requirements.txt
fi

export STORE_BACKEND="${STORE_BACKEND:-local}"
export LOCAL_STORE_PATH="${LOCAL_STORE_PATH:-./atlas_data}"
export APP_PORT="${APP_PORT:-8080}"

# Source .env if present
[ -f .env ] && set -a && . ./.env && set +a

echo "==> Atlas on http://localhost:${APP_PORT} (store=${STORE_BACKEND})"
exec ./.venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port "${APP_PORT}" --reload
