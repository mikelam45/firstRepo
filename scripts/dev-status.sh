#!/usr/bin/env bash
# Report whether the Mac development server is answering on loopback.
set -euo pipefail
PORT="${PORT:-8099}"
url="http://127.0.0.1:${PORT}/health"
if ! body="$(curl -fsS --max-time 2 "$url" 2>/dev/null)"; then
  echo "nothing is listening on 127.0.0.1:${PORT}"
  exit 1
fi
printf '%s\n' "$body"
