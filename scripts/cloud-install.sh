#!/usr/bin/env bash
# Idempotent dependency install for the cloud agent and for local setup.
# Prefers python3.12, then python3.13, then python3 (often Homebrew 3.14 on a new Mac).
set -euo pipefail
cd "$(dirname "$0")/.."

fail_need_python() {
  echo "Need Python 3.12 or 3.13 (3.14 works only with the pinned wheels)." >&2
  echo "Install Python 3.12 from python.org or \`brew install python@3.12\`, then \`rm -rf .venv\` and rerun \`bash scripts/dev.sh\`." >&2
  exit 1
}

python_mm() {
  "$1" -c 'import sys; print("%d.%d" % (sys.version_info.major, sys.version_info.minor))'
}

python_full() {
  "$1" -c 'import sys; print(sys.version.split()[0])'
}

# Pins in backend/requirements.txt publish wheels for 3.12–3.14.
is_supported_mm() {
  case "$1" in
    3.12|3.13|3.14) return 0 ;;
    *) return 1 ;;
  esac
}

pick_python() {
  local candidate resolved mm
  for candidate in python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      resolved="$(command -v "$candidate")"
      if ! mm="$(python_mm "$resolved" 2>/dev/null)"; then
        continue
      fi
      if is_supported_mm "$mm"; then
        printf '%s\n' "$resolved"
        return 0
      fi
    fi
  done
  return 1
}

create_venv() {
  local py="$1"
  if "$py" -m venv .venv; then
    return 0
  fi
  rm -rf .venv
  if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3-venv
    "$py" -m venv .venv
    return 0
  fi
  echo "Could not create a virtualenv with $py." >&2
  echo "On a Mac, install Python 3.12 from python.org or \`brew install python@3.12\`, then \`rm -rf .venv\` and rerun \`bash scripts/dev.sh\`." >&2
  exit 1
}

if ! PYTHON="$(pick_python)"; then
  fail_need_python
fi

SELECTED_MM="$(python_mm "$PYTHON")"
SELECTED_FULL="$(python_full "$PYTHON")"
echo "Using $PYTHON (Python $SELECTED_FULL)"

RECREATE=1
if [ -x .venv/bin/python ]; then
  EXISTING_MM="$(python_mm .venv/bin/python 2>/dev/null || true)"
  if [ "${EXISTING_MM}" = "3.12" ] || [ "${EXISTING_MM}" = "3.13" ]; then
    RECREATE=0
  elif [ "${EXISTING_MM}" = "3.14" ] && is_supported_mm "3.14"; then
    # Pinned pydantic-core publishes cp314 wheels, so a 3.14 venv is usable.
    RECREATE=0
  elif [ "${EXISTING_MM}" = "3.14" ] && command -v python3.12 >/dev/null 2>&1; then
    echo "Existing .venv is Python ${EXISTING_MM}; recreating with python3.12."
    PYTHON="$(command -v python3.12)"
    SELECTED_MM="$(python_mm "$PYTHON")"
    SELECTED_FULL="$(python_full "$PYTHON")"
    echo "Using $PYTHON (Python $SELECTED_FULL)"
    RECREATE=1
  fi
fi

if [ "$RECREATE" -eq 1 ]; then
  rm -rf .venv
  create_venv "$PYTHON"
fi

VENV_PY=".venv/bin/python"
VENV_MM="$(python_mm "$VENV_PY")"
VENV_FULL="$(python_full "$VENV_PY")"
echo "Virtualenv interpreter: $VENV_PY (Python $VENV_FULL)"

if ! is_supported_mm "$VENV_MM"; then
  echo "Python $VENV_FULL is not supported by the pinned dependencies." >&2
  echo "Install Python 3.12 from python.org or \`brew install python@3.12\`, then \`rm -rf .venv\` and rerun \`bash scripts/dev.sh\`." >&2
  exit 1
fi

.venv/bin/pip install --upgrade pip

# On 3.14+, refuse a source build of pydantic-core (PyO3 on older pins maxes out at 3.13).
PIP_INSTALL=(.venv/bin/pip install)
case "$VENV_MM" in
  3.14)
    PIP_INSTALL+=(--only-binary=pydantic-core)
    ;;
esac

if ! "${PIP_INSTALL[@]}" -r backend/requirements.txt; then
  echo "Pinned pydantic-core has no installable wheel for Python $VENV_FULL; refusing a Rust compile." >&2
  echo "Install Python 3.12 from python.org or \`brew install python@3.12\`, then \`rm -rf .venv\` and rerun \`bash scripts/dev.sh\`." >&2
  exit 1
fi
