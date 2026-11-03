#!/usr/bin/env bash
# Foreground dev server. Used by the cloud agent on boot.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/uvicorn ]; then
  echo "Python environment is missing. Run scripts/cloud-install.sh first." >&2
  exit 1
fi
if [ ! -f .env.development ]; then
  cp .env.development.example .env.development
fi
set -a
# shellcheck disable=SC1091
source .env.development
set +a
if [ "${APP_ENV}" != "development" ]; then
  echo "cloud-start.sh only runs APP_ENV=development." >&2
  exit 1
fi
mkdir -p "${DATA_DIR:-data}"
exec .venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "${PORT:-8000}"
