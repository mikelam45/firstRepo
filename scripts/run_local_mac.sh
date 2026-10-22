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
  echo "==> OpenRouter key in .env:"
  if grep -qE '^OPENROUTER_API_KEY=["'\'']?sk-or-v1-' .env 2>/dev/null; then
    echo "  OPENROUTER_API_KEY: set"
  else
    echo "  OPENROUTER_API_KEY: MISSING (set in .env)"
  fi
  if grep -q 'openrouter.ai' .env 2>/dev/null; then
    echo "  API_URL: openrouter.ai"
  else
    echo "  API_URL: check .env (expected openrouter.ai)"
  fi
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
  echo "==> Created .env from .env.example — add your OPENROUTER_API_KEY"
fi

# Keep Mac loopback + OpenRouter defaults without overwriting a real API key.
python3 - <<'PY'
from pathlib import Path
import re

p = Path(".env")
text = p.read_text(encoding="utf-8")
replacements = {
    "HOST": "127.0.0.1",
    "PORT": "3036",
    "ROLE_CONFIG_PATH": "./config/role_requirements.yaml",
    "OUTPUT_DIR": "./output/candidate_reviews",
    "API_URL": "https://openrouter.ai/api/v1/chat/completions",
    "LLM_BASE_URL": "https://openrouter.ai/api/v1",
}
# Only set MODEL_NAME if missing
if not re.search(r"^MODEL_NAME=", text, re.MULTILINE):
    replacements["MODEL_NAME"] = "qwen/qwen3-32b"

for key, value in replacements.items():
    pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
    line = f'{key}="{value}"' if key != "PORT" else f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        text = text.rstrip() + "\n" + line + "\n"
p.write_text(text, encoding="utf-8")
print("==> .env MacBook-local OpenRouter settings refreshed (key left as-is)")
PY

mkdir -p output/candidate_reviews

if ! grep -qE '^OPENROUTER_API_KEY=["'\'']?sk-or-v1-' .env 2>/dev/null \
  && ! grep -qE '^LLM_API_KEY=["'\'']?sk-or-v1-' .env 2>/dev/null; then
  echo "!! Warning: set OPENROUTER_API_KEY in .env (UI will start; LLM test needs the key)."
else
  echo "==> OpenRouter API key present in .env"
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
# Drop stale RHOAI overrides if any were exported earlier in the shell.
unset CERT_FILE TOKEN_FILE RHOAI_LLM_HOST RHOAI_LLM_IP 2>/dev/null || true

echo
echo "============================================"
echo "  MacBook local only (not VPS / not Cursor Cloud)"
echo "  OPEN ON THIS MAC: http://127.0.0.1:${PORT}"
echo "  Health check:     http://127.0.0.1:${PORT}/health"
echo "  LLM:              OpenRouter (${MODEL_NAME:-qwen/qwen3-32b})"
echo "  Leave this terminal open (Ctrl+C to stop)"
echo "============================================"
echo
exec python -m candidate_eval.cli serve --host "$BIND_HOST" --port "$PORT"
