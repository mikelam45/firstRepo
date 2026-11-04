#!/usr/bin/env bash
# Start the production stack on a Linux VPS. Requires Docker.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env.production ]; then
  echo "Create .env.production from .env.production.example on the VPS first." >&2
  exit 1
fi
if grep -Eq '^APP_ENV=development[[:space:]]*$' .env.production; then
  echo "Refusing to start the VPS with APP_ENV=development." >&2
  exit 1
fi
if ! grep -Eq '^APP_ENV=production[[:space:]]*$' .env.production; then
  echo ".env.production must set APP_ENV=production." >&2
  exit 1
fi
if grep -Eq '^PORTAL_API_TOKEN=(replace-with-a-long-random-token)?[[:space:]]*$' .env.production; then
  echo "Set a real PORTAL_API_TOKEN in .env.production before starting." >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required on the VPS. Install Docker Engine, then rerun scripts/vps-up.sh." >&2
  exit 1
fi
docker compose -f compose.prod.yaml up -d --build
docker compose -f compose.prod.yaml ps
