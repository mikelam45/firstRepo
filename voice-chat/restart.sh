#!/usr/bin/env bash
# Restart LingoCoach: free PORT, then start via run-local.sh (key/venv/pip stay there).
# Does not call itself; run-local.sh must not call this script.
set -euo pipefail
cd "$(dirname "$0")"
export PORT="${PORT:-8066}"

# shellcheck source=local-common.sh
. ./local-common.sh

echo "LingoCoach: stopping…"
if force_stop_port; then
  echo "LingoCoach: stopped"
else
  echo "LingoCoach: port ${PORT} still busy after force-stop; run-local.sh will try again."
fi

echo "LingoCoach: starting…"
exec ./run-local.sh
