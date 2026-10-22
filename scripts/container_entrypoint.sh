#!/usr/bin/env bash
# Container entrypoint for local Podman/Docker runs.
set -euo pipefail

cmd="${1:-serve}"
shift || true

export PYTHONPATH="/app/src:${PYTHONPATH:-}"
export PORT="${PORT:-3036}"
export HOST="${HOST:-0.0.0.0}"

case "${cmd}" in
  smoke)
    exec python -m candidate_eval.cli smoke "$@"
    ;;
  review)
    exec python -m candidate_eval.cli review "$@"
    ;;
  serve)
    exec python -m candidate_eval.cli serve "$@"
    ;;
  shell)
    exec bash "$@"
    ;;
  *)
    exec python -m candidate_eval.cli "${cmd}" "$@"
    ;;
esac
