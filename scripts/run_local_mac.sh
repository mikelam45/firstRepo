#!/usr/bin/env bash
# Run the Candidate Evaluation portal on a Mac (port 3036).
#
#   bash scripts/run_local_mac.sh           # start portal
#   bash scripts/run_local_mac.sh doctor    # diagnose reachability
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-3036}"
# Bind all interfaces so localhost + LAN both work; open via 127.0.0.1 in browser.
BIND_HOST="${BIND_HOST:-0.0.0.0}"

doctor() {
  echo "==> Repo: $ROOT"
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
  echo "==> Secrets"
  [[ -f SSLcert/qwen-tls.crt ]] && echo "  cert: present" || echo "  cert: MISSING (LLM test will fail; UI can still open)"
  [[ -f SSLcert/token_qwen3_8.txt ]] && echo "  token: present" || echo "  token: MISSING (LLM test will fail; UI can still open)"
}

if [[ "${1:-}" == "doctor" ]]; then
  doctor
  exit 0
fi

echo "==> Repo: $ROOT"
echo "==> Will serve http://127.0.0.1:${PORT}  (bind ${BIND_HOST}:${PORT})"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Created .env from .env.example"
fi

# Mac bare-metal paths (not container)
python3 - <<'PY'
from pathlib import Path
p = Path(".env")
t = p.read_text()
repl = {
    'ROLE_CONFIG_PATH="/app/config/role_requirements.yaml"': 'ROLE_CONFIG_PATH="./config/role_requirements.yaml"',
    'OUTPUT_DIR="/data/output"': 'OUTPUT_DIR="./output/candidate_reviews"',
    'CERT_FILE="/app/SSLcert/qwen-tls.crt"': 'CERT_FILE="./SSLcert/qwen-tls.crt"',
    'TOKEN_FILE="/app/SSLcert/token_qwen3_8.txt"': 'TOKEN_FILE="./SSLcert/token_qwen3_8.txt"',
}
for a, b in repl.items():
    t = t.replace(a, b)
p.write_text(t)
PY

mkdir -p SSLcert output/candidate_reviews

# Auto-pick up common download names if exact files are missing
if [[ ! -f SSLcert/qwen-tls.crt ]]; then
  for cand in \
    "$HOME/Downloads/qwen-tls.crt" \
    "$HOME/Downloads/qwen-tls"*.crt \
    ./qwen-tls.crt; do
    # shellcheck disable=SC2086
    if compgen -G "$cand" >/dev/null 2>&1; then
      src="$(compgen -G "$cand" | head -1)"
      cp "$src" SSLcert/qwen-tls.crt
      echo "==> Copied cert from $src -> SSLcert/qwen-tls.crt"
      break
    fi
  done
fi
if [[ ! -f SSLcert/token_qwen3_8.txt ]]; then
  for cand in \
    "$HOME/Downloads/token_qwen3_8.txt" \
    "$HOME/Downloads/token_qwen"*.txt \
    ./token_qwen3_8.txt; do
    if compgen -G "$cand" >/dev/null 2>&1; then
      src="$(compgen -G "$cand" | head -1)"
      cp "$src" SSLcert/token_qwen3_8.txt
      echo "==> Copied token from $src -> SSLcert/token_qwen3_8.txt"
      break
    fi
  done
fi

if [[ ! -f SSLcert/qwen-tls.crt || ! -f SSLcert/token_qwen3_8.txt ]]; then
  echo "!! Warning: place secrets here (exact names):"
  echo "     $ROOT/SSLcert/qwen-tls.crt"
  echo "     $ROOT/SSLcert/token_qwen3_8.txt"
  echo "   Portal UI will still start; LLM test needs those files."
else
  echo "==> Secrets OK:"
  echo "     $ROOT/SSLcert/qwen-tls.crt"
  echo "     $ROOT/SSLcert/token_qwen3_8.txt"
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

# Free a stale listener on this port if it is our previous serve
if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> Port ${PORT} already in use:"
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN || true
  echo "    If this is an old portal, stop it (Ctrl+C in that terminal) or: kill \$(lsof -t -iTCP:${PORT} -sTCP:LISTEN)"
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
export HOST="$BIND_HOST"
export PORT
export ROLE_CONFIG_PATH="${ROLE_CONFIG_PATH:-./config/role_requirements.yaml}"
export OUTPUT_DIR="${OUTPUT_DIR:-./output/candidate_reviews}"
export CERT_FILE="${CERT_FILE:-./SSLcert/qwen-tls.crt}"
export TOKEN_FILE="${TOKEN_FILE:-./SSLcert/token_qwen3_8.txt}"

echo
echo "============================================"
echo "  OPEN IN BROWSER:  http://127.0.0.1:${PORT}"
echo "  Health check:     http://127.0.0.1:${PORT}/health"
echo "  Leave this terminal open (Ctrl+C to stop)"
echo "============================================"
echo
exec python -m candidate_eval.cli serve --host "$BIND_HOST" --port "$PORT"
