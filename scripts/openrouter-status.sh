#!/usr/bin/env bash
# Check the Mac OpenRouter key file and the portal status without printing the key.
# Empty curl bodies are reported as such instead of python json.tool crashing with
# "Expecting value: line 1 column 1 (char 0)".
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8099}"
MAC_OPENROUTER_KEY_FILE="${MAC_OPENROUTER_KEY_FILE:-/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal}"

print_json_or_explain() {
  local label="$1"
  local http_code="$2"
  local body="$3"
  echo "${label}: HTTP ${http_code}"
  if [ -z "$body" ]; then
    echo "${label}: empty body (nothing to parse as JSON)."
    return 1
  fi
  case "$body" in
    \{*|\[*)
      if command -v python3 >/dev/null 2>&1; then
        if printf '%s' "$body" | python3 -m json.tool 2>/dev/null; then
          return 0
        fi
      fi
      echo "${label}: body is not valid JSON."
      printf '%s\n' "$body"
      return 1
      ;;
    *)
      echo "${label}: body is not JSON."
      printf '%s\n' "$body"
      return 1
      ;;
  esac
}

echo "OpenRouter key file: ${MAC_OPENROUTER_KEY_FILE}"
if [ -f "${MAC_OPENROUTER_KEY_FILE}" ]; then
  echo "key file: present"
else
  echo "key file: missing"
fi

if [ -x .venv/bin/python ]; then
  PYTHONPATH=backend .venv/bin/python - <<'PY'
from app.openrouter_key import MAC_KEY_PATH, load_openrouter_api_key, probe_openrouter, read_key_file
print("mac_key_exists", MAC_KEY_PATH.is_file())
file_key = read_key_file(MAC_KEY_PATH) if MAC_KEY_PATH.is_file() else None
loaded = load_openrouter_api_key()
print("key_loaded", bool(loaded or file_key))
print("probe", probe_openrouter(loaded or file_key, timeout=15.0))
PY
else
  echo "venv python: missing (run bash scripts/dev.sh first)"
fi

echo
url="http://127.0.0.1:${PORT}"
echo "Portal: ${url}"
if ! curl -fsS --max-time 2 "${url}/health" >/dev/null 2>&1; then
  echo "portal: not listening on 127.0.0.1:${PORT}"
  echo "Start it with: bash scripts/dev.sh"
  echo "Then re-run: bash scripts/openrouter-status.sh"
  echo "If the page still fails: bash scripts/dev-status.sh and lsof -nP -iTCP:${PORT} -sTCP:LISTEN"
  exit 1
fi

health_tmp="$(mktemp)"
test_tmp="$(mktemp)"
trap 'rm -f "$health_tmp" "$test_tmp"' EXIT

health_code="$(curl -sS --max-time 8 -o "$health_tmp" -w '%{http_code}' "${url}/health" || true)"
test_code="$(curl -sS --max-time 15 -o "$test_tmp" -w '%{http_code}' -X POST "${url}/api/openrouter/test" || true)"
health_body="$(cat "$health_tmp")"
test_body="$(cat "$test_tmp")"

print_json_or_explain "health" "$health_code" "$health_body" || true
print_json_or_explain "openrouter_test" "$test_code" "$test_body" || true

if [ "$health_code" != "200" ] || [ "$test_code" != "200" ]; then
  exit 1
fi
