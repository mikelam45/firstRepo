#!/usr/bin/env bash
# MacBook (and Linux) development server with reload.
# Refuses to start a production configuration.
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/cloud-install.sh
if [ ! -f .env.development ]; then
  cp .env.development.example .env.development
fi
set -a
# shellcheck disable=SC1091
source .env.development
set +a
if [ "${APP_ENV}" != "development" ]; then
  echo "scripts/dev.sh is the Mac development environment." >&2
  echo "On the VPS, copy .env.production.example to .env.production and run scripts/vps-up.sh." >&2
  exit 1
fi
mkdir -p "${DATA_DIR:-data}"
exec .venv/bin/uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port "${PORT:-8000}"
