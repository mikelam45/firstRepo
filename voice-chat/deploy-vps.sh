#!/usr/bin/env bash
# Deploy / restart LingoCoach on an Ubuntu VPS on port 8066.
#
# Prefer Podman (PRD §21.5). If Podman is missing, fall back to ./restart.sh
# (same venv + uvicorn path as the Mac).
#
# Never prints the OpenRouter key. Never copies secrets into the image or git.
#
# Usage (from voice-chat/ on the VPS):
#   ./deploy-vps.sh              # build + run (podman) or restart.sh
#   ./deploy-vps.sh --systemd    # also install the quadlet unit
#   ./deploy-vps.sh --local      # force restart.sh path (no container)
#   PORT=8066 ./deploy-vps.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8066}"
IMAGE="${LINGOCOACH_IMAGE:-lingocoach:revOct23}"
CONTAINER_NAME="${LINGOCOACH_CONTAINER:-lingocoach}"
MODE="auto" # auto | podman | local | systemd

for arg in "$@"; do
  case "$arg" in
    --systemd) MODE="systemd" ;;
    --local) MODE="local" ;;
    --podman) MODE="podman" ;;
    -h|--help)
      sed -n '2,13p' "${SCRIPT_DIR}/deploy-vps.sh"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

# Resolve env file. Prefer PRD path ~/lingocoach.env, then voice-chat/.env.
# Do not create the file; the operator must place secrets (mode 600).
# Accepts OpenRouter and/or TOTP assignments (values never printed).
resolve_env_file() {
  local candidates=(
    "${LINGOCOACH_ENV_FILE:-}"
    "${HOME}/lingocoach.env"
    "$(pwd)/.env"
  )
  local f
  for f in "${candidates[@]}"; do
    [[ -n "$f" && -f "$f" ]] || continue
    if grep -qE '^[[:space:]]*(export[[:space:]]+)?(OPENROUTER_API_KEY|LINGOCOACH_TOTP_SECRET|TOTP_SECRET)=' "$f" \
      || [[ "$(grep -cve '^[[:space:]]*$' "$f" || true)" == "1" ]]; then
      printf '%s' "$f"
      return 0
    fi
  done
  return 1
}

health_check() {
  local url="http://127.0.0.1:${PORT}/health"
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "LingoCoach: health ok at ${url}"
      return 0
    fi
    sleep 1
  done
  echo "LingoCoach: health check failed for ${url}" >&2
  return 1
}

free_port_host() {
  # Best-effort: stop our container or uvicorn holding PORT.
  if command -v podman >/dev/null 2>&1; then
    podman stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    podman rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  if [[ -x ./restart.sh ]]; then
    # shellcheck source=local-common.sh
    . ./local-common.sh
    force_stop_port || true
  fi
}

run_local() {
  echo "LingoCoach: using ./restart.sh (venv + uvicorn on 0.0.0.0:${PORT})"
  export PORT
  # restart.sh execs run-local.sh in the foreground; for VPS we background it.
  if [[ -t 1 ]]; then
    # Interactive: leave in foreground so logs stream (same as Mac).
    exec ./restart.sh
  fi
  nohup ./restart.sh >>"${HOME}/lingocoach-uvicorn.log" 2>&1 &
  echo "LingoCoach: started in background (log: ${HOME}/lingocoach-uvicorn.log)"
  health_check
}

run_podman() {
  local env_file=""
  if env_file="$(resolve_env_file)"; then
    echo "LingoCoach: using env file ${env_file} (contents not printed)."
    chmod 600 "$env_file" 2>/dev/null || true
    if grep -qE '^[[:space:]]*(export[[:space:]]+)?(LINGOCOACH_TOTP_SECRET|TOTP_SECRET)=' "$env_file"; then
      echo "LingoCoach: TOTP gate will be enabled (secret from env file)."
    else
      echo "LingoCoach: TOTP not in env file (optional: add LINGOCOACH_TOTP_SECRET=…)."
    fi
  else
    echo "LingoCoach: no env file found."
    echo "  Create ${HOME}/lingocoach.env (mode 600) with:"
    echo "    OPENROUTER_API_KEY=..."
    echo "    LINGOCOACH_TOTP_SECRET=...   # optional; recommended on a public VPS"
    echo "  Or voice-chat/.env. App still starts; live turns need the key."
  fi

  echo "LingoCoach: building image ${IMAGE}…"
  podman build -t "$IMAGE" .

  free_port_host

  local run_args=(
    --replace
    --name "$CONTAINER_NAME"
    --read-only
    --tmpfs /tmp
    --cap-drop=ALL
    --security-opt=no-new-privileges
    -p "0.0.0.0:${PORT}:8066"
  )
  if [[ -n "${env_file}" ]]; then
    run_args+=(--env-file "$env_file")
  else
    [[ -n "${OPENROUTER_API_KEY:-}" ]] && run_args+=(-e OPENROUTER_API_KEY)
    [[ -n "${LINGOCOACH_TOTP_SECRET:-}" ]] && run_args+=(-e LINGOCOACH_TOTP_SECRET)
    [[ -n "${TOTP_SECRET:-}" ]] && run_args+=(-e TOTP_SECRET)
  fi

  echo "LingoCoach: starting container on 0.0.0.0:${PORT}…"
  podman run -d "${run_args[@]}" "$IMAGE"
  health_check
}

install_systemd() {
  local unit_src unit_dir env_file=""
  unit_src="$(pwd)/lingocoach.container"
  unit_dir="${HOME}/.config/containers/systemd"

  [[ -f "$unit_src" ]] || {
    echo "Missing ${unit_src}" >&2
    exit 1
  }

  mkdir -p "$unit_dir"
  cp "$unit_src" "${unit_dir}/lingocoach.container"

  if env_file="$(resolve_env_file)"; then
    if [[ "$env_file" != "${HOME}/lingocoach.env" ]]; then
      # Quadlet defaults to %h/lingocoach.env; symlink if we found another file.
      ln -sfn "$env_file" "${HOME}/lingocoach.env"
      echo "LingoCoach: linked ${HOME}/lingocoach.env -> ${env_file}"
    fi
    chmod 600 "$env_file" 2>/dev/null || true
  else
    echo "LingoCoach: create ${HOME}/lingocoach.env (mode 600) before enable."
  fi

  echo "LingoCoach: building image for systemd unit…"
  podman build -t "$IMAGE" .

  systemctl --user daemon-reload
  systemctl --user enable --now lingocoach.service
  health_check
  echo "LingoCoach: systemd user unit lingocoach.service is active."
  echo "  Logs: journalctl --user -u lingocoach.service -f"
}

# --- entry ---
case "$MODE" in
  local)
    run_local
    ;;
  systemd)
    if ! command -v podman >/dev/null 2>&1; then
      echo "Podman required for --systemd. Install: sudo apt-get install -y podman" >&2
      exit 1
    fi
    install_systemd
    ;;
  podman)
    if ! command -v podman >/dev/null 2>&1; then
      echo "Podman not found." >&2
      exit 1
    fi
    run_podman
    ;;
  auto)
    if command -v podman >/dev/null 2>&1; then
      run_podman
    else
      echo "LingoCoach: Podman not installed; falling back to ./restart.sh"
      run_local
    fi
    ;;
esac
