#!/usr/bin/env bash
# Run LingoCoach on this machine, port 8066. Podman comes later.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8066}"

candidates=(
  "${LINGOCOACH_ENV_FILE:-}"
  "/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat"
  "$HOME/firstRepo/openrouter_key/.env_voice_chat"
)
for file in "${candidates[@]}"; do
  if [[ -n "$file" && -f "$file" ]]; then
    if grep -q '^OPENROUTER_API_KEY=' "$file"; then
      set -a
      # shellcheck disable=SC1090
      source "$file"
      set +a
    else
      OPENROUTER_API_KEY="$(tr -d '[:space:]' < "$file")"
      export OPENROUTER_API_KEY
    fi
    break
  fi
done

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q -r requirements.txt
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
