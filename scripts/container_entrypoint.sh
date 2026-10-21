#!/usr/bin/env bash
# Container entrypoint for local Podman/Docker runs.
set -euo pipefail

cmd="${1:-smoke}"
shift || true

export PYTHONPATH="/app/src:${PYTHONPATH:-}"

case "${cmd}" in
  smoke)
    exec python -m candidate_eval.cli smoke "$@"
    ;;
  review)
    exec python -m candidate_eval.cli review "$@"
    ;;
  shell)
    exec bash "$@"
    ;;
  *)
    exec python -m candidate_eval.cli "${cmd}" "$@"
    ;;
esac
