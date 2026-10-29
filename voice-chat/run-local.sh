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

# Deduplicate numeric PIDs, one per line. Avoids bash-4 associative arrays (macOS bash 3.2).
uniq_pids() {
  printf '%s\n' "$@" | grep -E '^[0-9]+$' | sort -n -u || true
}

# Return unique PIDs listening on TCP PORT (macOS + Linux).
# Prefer lsof LISTEN filter; also try fuser and /proc/net on Linux.
port_pids() {
  local found="" pid inode hex_port fd link

  if command -v lsof >/dev/null 2>&1; then
    # Prefer explicit LISTEN filter (macOS + Linux; covers IPv4/IPv6).
    found="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
    # Older/quirkier lsof spelling as backup.
    if [[ -z "$found" ]]; then
      found="$(lsof -nP -ti "tcp:$PORT" 2>/dev/null || true)"
    fi
  fi

  if command -v fuser >/dev/null 2>&1; then
    found="${found}"$'\n'"$(fuser "${PORT}/tcp" 2>/dev/null | tr -cs '0-9' '\n' || true)"
  fi

  # Linux /proc fallback: map listening inode -> pid via /proc/*/fd.
  if [[ -z "$(printf '%s' "$found" | grep -E '^[0-9]+$' || true)" && -r /proc/net/tcp ]]; then
    hex_port=$(printf '%04X' "$PORT")
    while IFS= read -r inode; do
      [[ -n "$inode" && "$inode" != "0" ]] || continue
      for fd in /proc/[0-9]*/fd/*; do
        link="$(readlink "$fd" 2>/dev/null || true)"
        if [[ "$link" == "socket:[${inode}]" ]]; then
          pid="$(printf '%s' "$fd" | cut -d/ -f3)"
          found="${found}"$'\n'"${pid}"
        fi
      done
    done <<EOF
$(awk -v hp="$hex_port" '
  NR > 1 {
    split($2, a, ":");
    if (toupper(a[2]) == hp && $4 == "0A") print $10
  }
' /proc/net/tcp /proc/net/tcp6 2>/dev/null)
EOF
  fi

  # shellcheck disable=SC2086
  uniq_pids $found
}

# Return 0 if PID is still alive.
proc_alive() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

# Return process command line for pid (macOS + Linux).
proc_cmdline() {
  local pid="$1" args
  if [[ -r "/proc/$pid/cmdline" ]]; then
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
    return 0
  fi
  args=$(ps -p "$pid" -o args= 2>/dev/null || true)
  printf '%s' "$args"
}

# Return 0 if this pid looks like our LingoCoach uvicorn (or python -m uvicorn).
# Case-insensitive on the process name so macOS "Python" matches.
is_lingocoach_pid() {
  local pid="$1"
  local comm args cwd comm_lc
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  [[ "$pid" -ne $$ ]] || return 1

  comm=$(ps -p "$pid" -o comm= 2>/dev/null || true)
  [[ -z "$comm" ]] && return 1
  # Strip path; macOS often reports "Python" with a capital P.
  comm="${comm##*/}"
  # trim whitespace
  comm="${comm#"${comm%%[![:space:]]*}"}"
  comm="${comm%"${comm##*[![:space:]]}"}"
  comm_lc=$(printf '%s' "$comm" | tr '[:upper:]' '[:lower:]')

  args=$(proc_cmdline "$pid")

  case "$comm_lc" in
    python|python[0-9]|python[0-9].*|uvicorn)
      if [[ "$args" == *uvicorn* || "$args" == *"app.main:app"* ]]; then
        return 0
      fi
      ;;
  esac

  # Any process whose cmdline is clearly our uvicorn invocation.
  if [[ "$args" == *"uvicorn"* && "$args" == *"app.main:app"* ]]; then
    return 0
  fi

  if [[ -e "/proc/$pid" ]]; then
    cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || true)
    if [[ "$cwd" == "$PWD" && ( "$comm_lc" == python* || "$comm_lc" == uvicorn ) ]]; then
      return 0
    fi
  fi

  return 1
}

# PIDs whose command line looks like our uvicorn for this PORT (port-find fallback).
uvicorn_cmd_pids() {
  local line pid args
  # ps -ax works on both macOS and Linux.
  ps -ax -o pid= -o args= 2>/dev/null | while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"
    pid="${line%%[[:space:]]*}"
    args="${line#"$pid"}"
    args="${args#"${args%%[![:space:]]*}"}"
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    [[ "$pid" -ne $$ ]] || continue
    if [[ "$args" == *"uvicorn"* && "$args" == *"app.main:app"* && "$args" == *"$PORT"* ]]; then
      printf '%s\n' "$pid"
    fi
  done
}

# SIGTERM, wait up to 5s, then SIGKILL. $1+ are PIDs (newline or space separated OK via "$@").
signal_pids() {
  local signaled="" pid waited still_alive

  for pid in "$@"; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    if kill -TERM "$pid" 2>/dev/null; then
      signaled="${signaled}"$'\n'"${pid}"
    fi
  done

  # Word-split on purpose: signaled is a newline/space list of PIDs.
  # shellcheck disable=SC2086
  signaled="$(printf '%s\n' $signaled | grep -E '^[0-9]+$' | sort -n -u || true)"
  [[ -n "$signaled" ]] || return 1

  echo "LingoCoach: stopped existing server on port ${PORT}."

  waited=0
  still_alive=1
  while [[ "$waited" -lt 5 && "$still_alive" -eq 1 ]]; do
    sleep 1
    still_alive=0
    while IFS= read -r pid; do
      [[ -n "$pid" ]] || continue
      if proc_alive "$pid"; then
        still_alive=1
        break
      fi
    done <<< "$signaled"
    waited=$((waited + 1))
  done

  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    if proc_alive "$pid"; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done <<< "$signaled"

  # Brief settle so the OS releases the listen socket (macOS can lag).
  sleep 1
  return 0
}

# Stop a previous LingoCoach uvicorn that is holding PORT.
# Finds listeners via lsof/fuser/proc, kills matching python/uvicorn PIDs,
# and falls back to cmdline match for "uvicorn app.main:app" + PORT.
stop_existing_server() {
  local pids pid to_kill=""

  pids=$(port_pids)

  if [[ -n "${pids:-}" ]]; then
    while IFS= read -r pid; do
      [[ -n "$pid" ]] || continue
      is_lingocoach_pid "$pid" || continue
      to_kill="${to_kill}"$'\n'"${pid}"
    done <<< "$pids"
  fi

  # If port-based discovery found nothing killable, match by uvicorn cmdline.
  if [[ -z "$(printf '%s' "$to_kill" | grep -E '^[0-9]+$' || true)" ]]; then
    while IFS= read -r pid; do
      [[ -n "$pid" ]] || continue
      to_kill="${to_kill}"$'\n'"${pid}"
    done <<< "$(uvicorn_cmd_pids)"
  fi

  # Word-split on purpose: to_kill is a newline/space list of PIDs.
  # shellcheck disable=SC2086
  to_kill="$(printf '%s\n' $to_kill | grep -E '^[0-9]+$' | sort -n -u || true)"
  [[ -n "$to_kill" ]] || return 0

  # shellcheck disable=SC2086
  signal_pids $to_kill || true
}

candidates=(
  "${LINGOCOACH_ENV_FILE:-}"
  "/Users/mikelam/firstRepo/openrouter_key/.env_voice_chat"
  "/Users/mikelam/firstRepo/voice-chat/.env"
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
  stop_existing_server
  if port_is_busy; then
    echo "LingoCoach: port ${PORT} is already in use. That older process is still the one answering. Stop it, then run ./run-local.sh again."
    exit 1
  fi
fi
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
