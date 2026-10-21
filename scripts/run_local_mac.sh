#!/usr/bin/env bash
# Run the Candidate Evaluation portal on a Mac (port 3036).
# Usage (from repo root):
#   bash scripts/run_local_mac.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-3036}"
HOST="${HOST:-127.0.0.1}"

echo "==> Repo: $ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Created .env from .env.example"
fi

# Ensure Mac-friendly paths in .env for bare-metal (not container mounts)
if grep -q 'ROLE_CONFIG_PATH="/app/config' .env 2>/dev/null; then
  sed -i.bak \
    -e 's|ROLE_CONFIG_PATH="/app/config/role_requirements.yaml"|ROLE_CONFIG_PATH="./config/role_requirements.yaml"|' \
    -e 's|OUTPUT_DIR="/data/output"|OUTPUT_DIR="./output/candidate_reviews"|' \
    .env || true
  rm -f .env.bak
fi

mkdir -p SSLcert output/candidate_reviews

if [[ ! -f SSLcert/qwen-tls.crt || ! -f SSLcert/token_qwen3_8.txt ]]; then
  cat <<EOF
!! Missing secrets under SSLcert/
   Need:
     SSLcert/qwen-tls.crt
     SSLcert/token_qwen3_8.txt
   Copy them into that folder, then re-run this script.
EOF
  exit 1
fi

LLM_HOST="${RHOAI_LLM_HOST:-redhataiqwen38-27b-int4-rhoai-test.apps.demo.rhoai.demo}"
LLM_IP="${RHOAI_LLM_IP:-192.168.147.135}"
if ! grep -q "$LLM_HOST" /etc/hosts 2>/dev/null; then
  echo "==> Adding /etc/hosts entry (may prompt for password):"
  echo "    $LLM_IP $LLM_HOST"
  echo "$LLM_IP $LLM_HOST" | sudo tee -a /etc/hosts >/dev/null
else
  echo "==> /etc/hosts already has $LLM_HOST"
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

export HOST PORT
set -a
# shellcheck disable=SC1091
source .env
set +a
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-3036}"
export ROLE_CONFIG_PATH="${ROLE_CONFIG_PATH:-./config/role_requirements.yaml}"
export OUTPUT_DIR="${OUTPUT_DIR:-./output/candidate_reviews}"
export CERT_FILE="${CERT_FILE:-./SSLcert/qwen-tls.crt}"
export TOKEN_FILE="${TOKEN_FILE:-./SSLcert/token_qwen3_8.txt}"

echo "==> Starting portal on http://${HOST}:${PORT}"
echo "    Ctrl+C to stop"
exec python -m candidate_eval.cli serve --host "$HOST" --port "$PORT"
