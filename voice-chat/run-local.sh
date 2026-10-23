#!/usr/bin/env bash
# Run LingoCoach on this machine, port 8066. Podman comes later.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8066}"

# Read one assignment line. Accept optional "export" and surrounding quotes.
# Never print the key. A raw one-line file is accepted when it has no spaces.
load_openrouter_key() {
  local file="$1" line key
  [[ -n "$file" && -f "$file" ]] || return 1
  line="$(grep -E '^[[:space:]]*(export[[:space:]]+)?OPENROUTER_API_KEY=' "$file" | tail -n 1 || true)"
  if [[ -n "$line" ]]; then
    key="${line#*=}"
    key="${key//$'\r'/}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    if [[ ${#key} -ge 2 && ( ( "$key" == \"*\" && "$key" == *\" ) || ( "$key" == \'*\' && "$key" == *\' ) ) ]]; then
      key="${key:1:${#key}-2}"
    fi
  elif [[ "$(grep -cve '^[[:space:]]*$' "$file" || true)" == "1" ]]; then
    key="$(grep -v '^[[:space:]]*$' "$file" | head -n 1)"
    key="${key//$'\r'/}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" != *" "* && "$key" != *=* ]] || key=""
  fi
  [[ -n "${key:-}" ]] || return 1
  export OPENROUTER_API_KEY="$key"
  return 0
}

# Return the PIDs that are listening on TCP PORT, one per line.
port_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$PORT" 2>/dev/null || true
  elif command -v fuser >/dev/null 2>&1; then
    fuser "$PORT"/tcp 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true
  fi
}

# Stop a previous LingoCoach uvicorn that is holding PORT.
# Only targets python/uvicorn processes listening on this port, and falls back
# to checking the process cwd on Linux. If nothing is listening, do nothing.
stop_existing_server() {
  local pids pid comm args killed=0

  pids=$(port_pids)

  if [[ -z "${pids:-}" ]]; then
    return 0
  fi

  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    [[ "$pid" -eq $$ ]] && continue

    comm=$(ps -p "$pid" -o comm= 2>/dev/null || true)
    [[ -z "$comm" ]] && continue

    args=$(ps -p "$pid" -o args= 2>/dev/null || true)

    local is_match=0
    case "$comm" in
      python|python3|python3.*|uvicorn)
        if [[ "$args" == *uvicorn* || "$args" == *"app.main:app"* ]]; then
          is_match=1
        fi
        ;;
    esac

    if [[ "$is_match" -eq 0 && -e "/proc/$pid" ]]; then
      local cwd
      cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || true)
      if [[ "$cwd" == "$PWD" && ("$comm" == python* || "$comm" == uvicorn) ]]; then
        is_match=1
      fi
    fi

    if [[ "$is_match" -eq 1 ]]; then
      if kill -TERM "$pid" 2>/dev/null; then
        killed=1
      fi
    fi
  done <<< "$pids"

  if [[ "$killed" -eq 1 ]]; then
    echo "LingoCoach: stopped existing server on port ${PORT}."
    local waited=0
    while [[ "$waited" -lt 5 ]]; do
      sleep 1
      local still
      still=$(port_pids)
      [[ -z "$still" ]] && break
      waited=$((waited + 1))
    done
    local leftover
    leftover=$(port_pids)
    if [[ -n "$leftover" ]]; then
      while IFS= read -r pid; do
        [[ "$pid" =~ ^[0-9]+$ ]] || continue
        kill -KILL "$pid" 2>/dev/null || true
      done <<< "$leftover"
    fi
  fi
}

candidates=(
  "${LINGOCOACH_ENV_FILE:-}"
  "/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat"
  "$HOME/firstRepo/openrouter_key/.env_voice_chat"
  "$(dirname "$0")/../openrouter_key/.env_voice_chat"
  "$(dirname "$0")/.env"
)
loaded=0
for file in "${candidates[@]}"; do
  if load_openrouter_key "$file"; then
    echo "LingoCoach: OpenRouter key loaded (${#OPENROUTER_API_KEY} characters)."
    loaded=1
    break
  fi
done
if [[ "$loaded" -eq 0 ]]; then
  echo "LingoCoach: no OpenRouter key. Replies use offline examples."
fi

stop_existing_server

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q -r requirements.txt
if .venv/bin/python - "$PORT" << 'PY'
import socket, sys
sock = socket.socket()
sock.settimeout(0.4)
try:
    sock.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(1)
else:
    sys.exit(0)
PY
then
  echo "LingoCoach: port ${PORT} is already in use. That older process is still the one answering. Stop it, then run ./run-local.sh again."
  exit 1
fi
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
