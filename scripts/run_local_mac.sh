#!/usr/bin/env bash
# MacBook-only local portal (no VPS / no Cursor Cloud).
#
#   bash scripts/run_local_mac.sh           # start portal on this Mac
#   bash scripts/run_local_mac.sh doctor    # diagnose reachability
#
# Open on THIS Mac only: http://127.0.0.1:3036
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PROJECT_ROOT="$ROOT"

PORT="${PORT:-3036}"
# Loopback only — not exposed as a public/VPS service.
BIND_HOST="${BIND_HOST:-127.0.0.1}"

# Absolute MacBook secret directory (not under the git repo)
SSL_DIR="${SSL_DIR:-/Users/mikelam/SSLcert}"
CERT_ABS="$SSL_DIR/qwen-tls.crt"
TOKEN_ABS="$SSL_DIR/token_qwen3_8.txt"
CERT_ENV="$CERT_ABS"
TOKEN_ENV="$TOKEN_ABS"

doctor() {
  echo "==> Repo: $ROOT"
  echo "==> PROJECT_ROOT=$PROJECT_ROOT"
  echo "==> Checking port ${PORT}..."
  if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null; then
    echo "OK: something is listening on ${PORT}"
  else
    echo "FAIL: nothing listening on ${PORT} (portal not running)"
  fi
  echo "==> curl http://127.0.0.1:${PORT}/health"
  if curl -sS -m 3 "http://127.0.0.1:${PORT}/health"; then
    echo
    echo "OK: portal reachable at http://127.0.0.1:${PORT}"
  else
    echo
    echo "FAIL: cannot curl health endpoint"
    echo "Start with: bash scripts/run_local_mac.sh"
  fi
  echo "==> Secrets (absolute Mac paths):"
  echo "  CERT_FILE=$CERT_ENV"
  if [[ -f "$CERT_ABS" ]]; then echo "       present"; else echo "       MISSING"; fi
  echo "  TOKEN_FILE=$TOKEN_ENV"
  if [[ -f "$TOKEN_ABS" ]]; then echo "       present"; else echo "       MISSING"; fi
}

if [[ "${1:-}" == "doctor" ]]; then
  doctor
  exit 0
fi

echo "==> Repo: $ROOT"
echo "==> PROJECT_ROOT=$PROJECT_ROOT"
echo "==> Will serve http://127.0.0.1:${PORT}  (bind ${BIND_HOST}:${PORT})"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Created .env from .env.example"
fi

# Force Mac absolute secret paths in .env
python3 - <<PY
from pathlib import Path
import re

p = Path(".env")
text = p.read_text(encoding="utf-8")
replacements = {
    "HOST": "127.0.0.1",
    "PORT": "3036",
    "ROLE_CONFIG_PATH": "./config/role_requirements.yaml",
    "OUTPUT_DIR": "./output/candidate_reviews",
    "CERT_FILE": "${CERT_ENV}",
    "TOKEN_FILE": "${TOKEN_ENV}",
}
for key, value in replacements.items():
    pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
    line = f'{key}="{value}"' if key != "PORT" else f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        text = text.rstrip() + "\n" + line + "\n"
p.write_text(text, encoding="utf-8")
print("==> .env MacBook-local paths:")
for key, value in replacements.items():
    print(f"     {key}={value}")
PY

mkdir -p "$SSL_DIR" output/candidate_reviews

# Auto-pick up common download names into /Users/mikelam/SSLcert
if [[ ! -f "$CERT_ABS" ]]; then
  for cand in \
    "$HOME/Downloads/qwen-tls.crt" \
    "$HOME/Downloads/qwen-tls"*.crt \
    "$ROOT/SSLcert/qwen-tls.crt" \
    ./qwen-tls.crt; do
    if compgen -G "$cand" >/dev/null 2>&1; then
      src="$(compgen -G "$cand" | head -1)"
      cp "$src" "$CERT_ABS"
      echo "==> Copied cert from $src -> $CERT_ABS"
      break
    fi
  done
fi
if [[ ! -f "$TOKEN_ABS" ]]; then
  for cand in \
    "$HOME/Downloads/token_qwen3_8.txt" \
    "$HOME/Downloads/token_qwen"*.txt \
    "$ROOT/SSLcert/token_qwen3_8.txt" \
    ./token_qwen3_8.txt; do
    if compgen -G "$cand" >/dev/null 2>&1; then
      src="$(compgen -G "$cand" | head -1)"
      cp "$src" "$TOKEN_ABS"
      echo "==> Copied token from $src -> $TOKEN_ABS"
      break
    fi
  done
fi

if [[ ! -f "$CERT_ABS" || ! -f "$TOKEN_ABS" ]]; then
  echo "!! Warning: place secrets here (exact absolute paths):"
  echo "     $CERT_ABS"
  echo "     $TOKEN_ABS"
  echo "   Portal UI will still start; LLM test needs those files."
else
  echo "==> Secrets OK (absolute):"
  echo "     $CERT_ABS"
  echo "     $TOKEN_ABS"
fi

LLM_HOST="${RHOAI_LLM_HOST:-redhataiqwen38-27b-int4-rhoai-test.apps.demo.rhoai.demo}"
LLM_IP="${RHOAI_LLM_IP:-192.168.147.135}"
if ! grep -q "$LLM_HOST" /etc/hosts 2>/dev/null; then
  echo "==> Trying to add /etc/hosts entry (optional; only needed for LLM, not the UI):"
  echo "    $LLM_IP $LLM_HOST"
  if echo "$LLM_IP $LLM_HOST" | sudo tee -a /etc/hosts >/dev/null; then
    echo "==> /etc/hosts updated"
  else
    echo "!! Could not update /etc/hosts (continuing anyway — UI will still work)"
  fi
else
  echo "==> /etc/hosts already has $LLM_HOST"
fi

# Free a stale listener on this port (common after a previous portal run)
if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> Port ${PORT} already in use — stopping old listener(s):"
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN || true
  # Prefer killing our previous serve; fall back to anything on the port.
  pkill -f "candidate_eval.cli serve" 2>/dev/null || true
  pkill -f "uvicorn.*candidate_eval" 2>/dev/null || true
  PIDS="$(lsof -t -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${PIDS}" ]]; then
    # shellcheck disable=SC2086
    kill ${PIDS} 2>/dev/null || true
    sleep 1
    PIDS="$(lsof -t -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${PIDS}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${PIDS} 2>/dev/null || true
      sleep 0.5
    fi
  fi
  if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "FAIL: port ${PORT} still busy. Free it manually:"
    echo "  lsof -nP -iTCP:${PORT} -sTCP:LISTEN"
    echo "  kill -9 \$(lsof -t -iTCP:${PORT} -sTCP:LISTEN)"
    exit 1
  fi
  echo "==> Port ${PORT} is free"
fi

if [[ ! -d .venv ]]; then
  echo "==> Creating Python venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q -e .

set -a
# shellcheck disable=SC1091
source .env
set +a
export PROJECT_ROOT="$ROOT"
export HOST="$BIND_HOST"
export PORT
export ROLE_CONFIG_PATH="${ROLE_CONFIG_PATH:-./config/role_requirements.yaml}"
export OUTPUT_DIR="${OUTPUT_DIR:-./output/candidate_reviews}"
# Always pin absolute Mac secret paths.
export CERT_FILE="$CERT_ENV"
export TOKEN_FILE="$TOKEN_ENV"

echo
echo "============================================"
echo "  MacBook local only (not VPS / not Cursor Cloud)"
echo "  OPEN ON THIS MAC: http://127.0.0.1:${PORT}"
echo "  Health check:     http://127.0.0.1:${PORT}/health"
echo "  CERT_FILE:        $CERT_FILE"
echo "       resolved:    $CERT_ABS"
echo "  TOKEN_FILE:       $TOKEN_FILE"
echo "       resolved:    $TOKEN_ABS"
echo "  Leave this terminal open (Ctrl+C to stop)"
echo "============================================"
echo
exec python -m candidate_eval.cli serve --host "$BIND_HOST" --port "$PORT"
