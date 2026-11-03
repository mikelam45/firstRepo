#!/usr/bin/env bash
# Idempotent dependency install for the cloud agent and for local setup.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! python3 -m venv .venv; then
  rm -rf .venv
  if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3-venv
    python3 -m venv .venv
  else
    echo "python3 could not create a virtualenv. On a Mac, install Python 3.12 from python.org and rerun scripts/dev.sh." >&2
    exit 1
  fi
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r backend/requirements.txt
