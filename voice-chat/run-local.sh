#!/usr/bin/env bash
# Run LingoCoach on this machine, port 8066. Podman comes later.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8066}"
# Bind address. Default public (Mac / HTTP VPS). deploy-vps.sh --https sets HOST=127.0.0.1.
HOST="${HOST:-0.0.0.0}"

# Shared stop/port helpers (also used by restart.sh).
# shellcheck source=local-common.sh
. ./local-common.sh

# Read KEY=value from a file. Accept optional "export" and surrounding quotes.
# Never print the value. For OPENROUTER_API_KEY only, a raw one-line file is OK.
load_env_assignment() {
  local file="$1" varname="$2" allow_raw="${3:-0}" line value
  [[ -n "$file" && -f "$file" ]] || return 1
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${varname}=" "$file" | tail -n 1 || true)"
  if [[ -n "$line" ]]; then
    value="${line#*=}"
    value="${value//$'\r'/}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ ${#value} -ge 2 && ( ( "$value" == \"*\" && "$value" == *\" ) || ( "$value" == \'*\' && "$value" == *\' ) ) ]]; then
      value="${value:1:${#value}-2}"
    fi
  elif [[ "$allow_raw" == "1" && "$(grep -cve '^[[:space:]]*$' "$file" || true)" == "1" ]]; then
    value="$(grep -v '^[[:space:]]*$' "$file" | head -n 1)"
    value="${value//$'\r'/}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    [[ "$value" != *" "* && "$value" != *=* ]] || value=""
  fi
  [[ -n "${value:-}" ]] || return 1
  printf -v "$varname" '%s' "$value"
  export "$varname"
  return 0
}

candidates=(
  "${LINGOCOACH_ENV_FILE:-}"
  "${HOME}/lingocoach.env"
  "/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat"
  "/Users/mikelam/firstRepo/voice-chat/.env"
  "$HOME/firstRepo/openrouter_key/.env_voice_chat"
  "$(dirname "$0")/../openrouter_key/.env_voice_chat"
  "$(dirname "$0")/.env"
)
loaded=0
for file in "${candidates[@]}"; do
  if load_env_assignment "$file" OPENROUTER_API_KEY 1; then
    echo "LingoCoach: OpenRouter key loaded (${#OPENROUTER_API_KEY} characters)."
    loaded=1
    break
  fi
done
if [[ "$loaded" -eq 0 ]]; then
  echo "LingoCoach: no OpenRouter key. Replies use offline examples."
fi

# Optional TOTP: prefer existing env, else load from the same env files (never echo).
# Alias TOTP_SECRET is accepted by the app; LINGOCOACH_TOTP_SECRET wins.
if [[ -z "${LINGOCOACH_TOTP_SECRET:-}" ]]; then
  for file in "${candidates[@]}"; do
    if load_env_assignment "$file" LINGOCOACH_TOTP_SECRET 0; then
      break
    fi
    if [[ -z "${TOTP_SECRET:-}" ]] && load_env_assignment "$file" TOTP_SECRET 0; then
      break
    fi
  done
fi
if [[ -n "${LINGOCOACH_TOTP_SECRET:-}" || -n "${TOTP_SECRET:-}" || -f .totp_secret ]]; then
  echo "LingoCoach: TOTP gate will be enabled."
else
  echo "LingoCoach: TOTP not configured (optional: set LINGOCOACH_TOTP_SECRET or run .venv/bin/python -m app.totp_setup)."
fi

LINGOCOACH_STOP_VERBOSE=1 stop_existing_server

# Debian/Ubuntu often create a .venv without pip (ensurepip disabled), or leave a
# half-broken tree after a failed first run. Repair before install.
ensure_venv_with_pip() {
  local need_recreate=0
  if [[ ! -x .venv/bin/python ]]; then
    need_recreate=1
  elif ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    echo "LingoCoach: .venv has no pip; bootstrapping…"
    if .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 \
      && .venv/bin/python -m pip --version >/dev/null 2>&1; then
      return 0
    fi
    need_recreate=1
  else
    return 0
  fi

  if [[ "$need_recreate" -eq 1 ]]; then
    echo "LingoCoach: creating .venv (with pip)…"
    rm -rf .venv
    if ! python3 -m venv --upgrade-deps .venv 2>/dev/null; then
      # Older python3-venv without --upgrade-deps
      if ! python3 -m venv .venv; then
        echo "LingoCoach: cannot create venv. On Debian/Ubuntu install:" >&2
        echo "  sudo apt-get install -y python3-venv python3-pip" >&2
        exit 1
      fi
      .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi
  fi

  if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    echo "LingoCoach: pip still missing inside .venv." >&2
    echo "  sudo apt-get install -y python3-venv python3-pip" >&2
    echo "  rm -rf .venv && ./run-local.sh" >&2
    exit 1
  fi
}

ensure_venv_with_pip
echo "LingoCoach: installing Python deps (may take a minute on first run)…"
.venv/bin/python -m pip install -q -r requirements.txt
echo "LingoCoach: deps ready"

# deploy-vps.sh --https runs this first in the foreground so health checks
# are not racing a cold pip install.
if [[ "${LINGOCOACH_PREPARE_ONLY:-0}" == "1" ]]; then
  echo "LingoCoach: prepare-only done (not starting uvicorn)."
  exit 0
fi

# Return 0 if something accepts TCP connections on PORT (IPv4).
port_is_busy() {
  .venv/bin/python - "$PORT" << 'PY'
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
}

if port_is_busy; then
  # Last chance: something still listening — kill our uvicorn again if present.
  LINGOCOACH_STOP_VERBOSE=1 stop_existing_server
  if port_is_busy; then
    echo "LingoCoach: port ${PORT} is already in use. That older process is still the one answering. Stop it, then run ./run-local.sh again."
    exit 1
  fi
fi
echo "LingoCoach: uvicorn on ${HOST}:${PORT}"
exec .venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
