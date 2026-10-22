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

# Rewrite .env to OpenRouter-only keys (preserve existing API key).
python3 - <<'PY'
from pathlib import Path
import re

p = Path(".env")
text = p.read_text(encoding="utf-8") if p.exists() else ""

def _get(key: str, default: str = "") -> str:
    m = re.search(rf"^{key}=(.*)$", text, re.MULTILINE)
    if not m:
        return default
    return m.group(1).strip().strip("\"'")

key = _get("OPENROUTER_API_KEY") or _get("LLM_API_KEY") or "sk-or-v1-REPLACE_ME"
model = _get("MODEL_NAME", "qwen/qwen3-32b")
if not model or "/" not in model:
    model = "qwen/qwen3-32b"
api_url = _get("API_URL", "https://openrouter.ai/api/v1/chat/completions")
if "openrouter.ai" not in api_url.lower():
    api_url = "https://openrouter.ai/api/v1/chat/completions"
referer = _get("OPENROUTER_HTTP_REFERER", "http://127.0.0.1:3036")
title = _get("OPENROUTER_APP_TITLE", "Candidate Evaluation")

p.write_text(
    "\n".join(
        [
            "# OpenRouter only — https://openrouter.ai/keys",
            f'OPENROUTER_API_KEY="{key}"',
            f'API_URL="{api_url}"',
            f'MODEL_NAME="{model}"',
            f'OPENROUTER_HTTP_REFERER="{referer}"',
            f'OPENROUTER_APP_TITLE="{title}"',
            "",
        ]
    ),
    encoding="utf-8",
)
print("==> .env reduced to OpenRouter-only settings")
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
export THUNDERBIRD_MAIL_PATH="${THUNDERBIRD_MAIL_PATH:-./fixtures/mbox}"
export TARGET_MAIL_FOLDER="${TARGET_MAIL_FOLDER:-Applications}"
export LOCAL_DB_PATH="${LOCAL_DB_PATH:-./data/candidate_eval.sqlite}"
export REVIEW_USE_LLM="${REVIEW_USE_LLM:-true}"
export LLM_API_KEY="${LLM_API_KEY:-$OPENROUTER_API_KEY}"
# Never use legacy cert/token for OpenRouter.
unset CERT_FILE TOKEN_FILE RHOAI_LLM_HOST RHOAI_LLM_IP ALLOW_LEGACY_TLS 2>/dev/null || true

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
