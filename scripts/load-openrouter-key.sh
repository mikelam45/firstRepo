#!/usr/bin/env bash
# Load an OpenRouter key into OPENROUTER_API_KEY without printing it.
# The Mac file is not executed: a one-line raw key must not run as a command.
# Missing files leave the key unset and return success.

MAC_OPENROUTER_KEY_FILE="${MAC_OPENROUTER_KEY_FILE:-/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal}"

_openrouter_strip_quotes() {
  local value="$1"
  value="${value%$'\r'}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  local length=${#value}
  if [ "$length" -ge 2 ]; then
    local first="${value:0:1}"
    local last="${value:length-1:1}"
    if [ "$first" = "$last" ] && { [ "$first" = '"' ] || [ "$first" = "'" ]; }; then
      value="${value:1:length-2}"
      value="${value#"${value%%[![:space:]]*}"}"
      value="${value%"${value##*[![:space:]]}"}"
    fi
  fi
  printf '%s' "$value"
}

# Read one dotenv or raw-key file. Does not print the key.
load_openrouter_key_file() {
  set +x
  local file="$1"
  if [ ! -f "$file" ] || [ ! -r "$file" ]; then
    return 0
  fi
  local line trimmed name value
  local api_key="" alt_key="" raw_key=""
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    trimmed="${line#"${line%%[![:space:]]*}"}"
    trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
    [ -z "$trimmed" ] && continue
    case "$trimmed" in
      \#*) continue ;;
    esac
    if [ "${trimmed#export }" != "$trimmed" ]; then
      trimmed="${trimmed#export }"
      trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}"
    fi
    case "$trimmed" in
      *=*)
        name="${trimmed%%=*}"
        name="${name%"${name##*[![:space:]]}"}"
        name="${name#"${name%%[![:space:]]*}"}"
        value="${trimmed#*=}"
        value="$(_openrouter_strip_quotes "$value")"
        if [ "$name" = "OPENROUTER_API_KEY" ]; then
          api_key="$value"
        elif [ "$name" = "OPENROUTER_KEY" ]; then
          alt_key="$value"
        fi
        ;;
      *)
        if [ -z "$raw_key" ]; then
          raw_key="$(_openrouter_strip_quotes "$trimmed")"
        fi
        ;;
    esac
  done < "$file"
  if [ -n "$api_key" ]; then
    export OPENROUTER_API_KEY="$api_key"
  elif [ -n "$alt_key" ]; then
    export OPENROUTER_API_KEY="$alt_key"
  elif [ -n "$raw_key" ]; then
    export OPENROUTER_API_KEY="$raw_key"
  fi
  return 0
}

# Process env, then OPENROUTER_ENV_FILE, then the Mac path.
# A set OPENROUTER_ENV_FILE that is missing does not fall through.
load_openrouter_key() {
  set +x
  local existing="${OPENROUTER_API_KEY:-}"
  existing="$(_openrouter_strip_quotes "$existing")"
  if [ -n "$existing" ]; then
    export OPENROUTER_API_KEY="$existing"
    return 0
  fi
  if [ -n "${OPENROUTER_ENV_FILE:-}" ]; then
    load_openrouter_key_file "${OPENROUTER_ENV_FILE}"
    return 0
  fi
  if [ -f "${MAC_OPENROUTER_KEY_FILE}" ]; then
    load_openrouter_key_file "${MAC_OPENROUTER_KEY_FILE}"
  fi
  return 0
}
