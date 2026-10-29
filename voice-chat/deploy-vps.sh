#!/usr/bin/env bash
# Deploy / restart LingoCoach on an Ubuntu VPS on port 8066.
#
# Prefer Podman (PRD §21.5). If Podman is missing, fall back to ./restart.sh
# (same venv + uvicorn path as the Mac).
#
# Never prints the OpenRouter key. Never copies secrets into the image or git.
# Never invents a public hostname — HTTPS needs LINGOCOACH_DOMAIN (or DOMAIN /
# VPS_HOST) that you supply.
#
# Usage (from voice-chat/ on the VPS):
#   ./deploy-vps.sh              # build + run (podman) or restart.sh
#   ./deploy-vps.sh --systemd    # also install the quadlet unit
#   ./deploy-vps.sh --local      # force restart.sh path (no container)
#   ./deploy-vps.sh --https      # bind app to 127.0.0.1 + Caddy TLS on 443
#   LINGOCOACH_DOMAIN=example.com ./deploy-vps.sh --https
#   PORT=8066 ./deploy-vps.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8066}"
IMAGE="${LINGOCOACH_IMAGE:-lingocoach:revOct23}"
CONTAINER_NAME="${LINGOCOACH_CONTAINER:-lingocoach}"
MODE="auto" # auto | podman | local | systemd
HTTPS=0

for arg in "$@"; do
  case "$arg" in
    --systemd) MODE="systemd" ;;
    --local) MODE="local" ;;
    --podman) MODE="podman" ;;
    --https) HTTPS=1 ;;
    -h|--help)
      sed -n '2,17p' "${SCRIPT_DIR}/deploy-vps.sh"
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

# Public DNS name for Let's Encrypt. Never invent one.
resolve_domain() {
  local d="${LINGOCOACH_DOMAIN:-${DOMAIN:-${VPS_HOST:-}}}"
  d="${d#"${d%%[![:space:]]*}"}"
  d="${d%"${d##*[![:space:]]}"}"
  # Strip accidental scheme / path / trailing slash / port
  d="${d#http://}"
  d="${d#https://}"
  d="${d%%/*}"
  d="${d%%:*}"
  printf '%s' "$d"
}

bind_host() {
  if [[ "$HTTPS" -eq 1 ]]; then
    printf '127.0.0.1'
  else
    printf '0.0.0.0'
  fi
}

health_check() {
  local url="http://127.0.0.1:${PORT}/health"
  local i
  local _try
  for _try in 1 2 3 4 5 6 7 8 9 10; do
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

render_caddyfile() {
  local domain="$1"
  local template="${SCRIPT_DIR}/Caddyfile.template"
  local out="$2"
  local email_block=""
  local email="${LINGOCOACH_ACME_EMAIL:-${ACME_EMAIL:-}}"

  [[ -f "$template" ]] || {
    echo "Missing ${template}" >&2
    exit 1
  }

  if [[ -n "$email" ]]; then
    # Let's Encrypt account contact (optional but recommended).
    email_block=$(printf '{\n\temail %s\n}\n' "$email")
  fi

  # Substitute placeholders. Domain must not contain spaces or newlines.
  if [[ "$domain" == *" "* || "$domain" == *$'\n'* ]]; then
    echo "Invalid domain (whitespace)." >&2
    exit 1
  fi

  local content
  content="$(cat "$template")"
  content="${content//__LINGOCOACH_DOMAIN__/${domain}}"
  content="${content//__ACME_EMAIL_BLOCK__/${email_block}}"
  printf '%s\n' "$content" >"$out"
}

install_caddy_https() {
  local domain tmp_cfg
  domain="$(resolve_domain)"
  if [[ -z "$domain" ]]; then
    echo "HTTPS requires a real DNS name." >&2
    echo "  Set LINGOCOACH_DOMAIN (preferred), or DOMAIN / VPS_HOST, then re-run with --https." >&2
    echo "  Example: LINGOCOACH_DOMAIN=coach.example.com ./deploy-vps.sh --https" >&2
    exit 1
  fi
  case "$domain" in
    YOUR_DOMAIN_HERE|your.domain.example|example.com|coach.example.com|*.invalid|*placeholder*)
      echo "Refusing placeholder domain '${domain}'. Use your real DNS name." >&2
      exit 1
      ;;
  esac

  echo "LingoCoach: HTTPS for domain ${domain} (Caddy → 127.0.0.1:${PORT})"
  if [[ -n "${LINGOCOACH_ACME_EMAIL:-${ACME_EMAIL:-}}" ]]; then
    echo "LingoCoach: ACME account email is set (value not printed)."
  else
    echo "LingoCoach: no ACME email (optional: LINGOCOACH_ACME_EMAIL=you@example.com)."
  fi

  if ! command -v caddy >/dev/null 2>&1; then
    echo "LingoCoach: installing Caddy (apt)…"
    if ! command -v sudo >/dev/null 2>&1; then
      echo "sudo + apt required to install Caddy, or install Caddy yourself and re-run." >&2
      exit 1
    fi
    sudo apt-get update
    sudo apt-get install -y caddy
  fi

  tmp_cfg="$(mktemp)"
  # shellcheck disable=SC2064
  trap "rm -f '$tmp_cfg'" RETURN
  render_caddyfile "$domain" "$tmp_cfg"

  echo "LingoCoach: validating Caddyfile…"
  if ! caddy validate --config "$tmp_cfg" --adapter caddyfile; then
    echo "Caddyfile validation failed. Config not installed." >&2
    exit 1
  fi

  if [[ ! -w /etc/caddy ]]; then
    if ! command -v sudo >/dev/null 2>&1; then
      echo "Need write access to /etc/caddy (or sudo)." >&2
      exit 1
    fi
    sudo mkdir -p /etc/caddy
    sudo cp "$tmp_cfg" /etc/caddy/Caddyfile
    sudo systemctl enable --now caddy
    sudo systemctl reload caddy
  else
    mkdir -p /etc/caddy
    cp "$tmp_cfg" /etc/caddy/Caddyfile
    systemctl enable --now caddy
    systemctl reload caddy
  fi

  echo "LingoCoach: Caddy reloaded. Visit https://${domain}/ (HTTP :80 redirects to HTTPS)."
  echo "  Ensure DNS A/AAAA for ${domain} points here, and ufw allows 80/tcp + 443/tcp."
  echo "  App stays on 127.0.0.1:${PORT}; do not open ${PORT}/tcp publicly when using --https."
}

run_local() {
  local host
  host="$(bind_host)"
  echo "LingoCoach: using ./restart.sh (venv + uvicorn on ${host}:${PORT})"
  export PORT
  if [[ "$HTTPS" -eq 1 ]]; then
    export LINGOCOACH_HTTPS=1
    # run-local.sh binds 0.0.0.0 by default; force loopback for HTTPS proxy mode.
    export HOST="${host}"
  fi
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
  local env_file="" host
  host="$(bind_host)"
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
    -p "${host}:${PORT}:8066"
  )
  if [[ "$HTTPS" -eq 1 ]]; then
    run_args+=(-e LINGOCOACH_HTTPS=1)
  fi
  if [[ -n "${env_file}" ]]; then
    run_args+=(--env-file "$env_file")
  else
    [[ -n "${OPENROUTER_API_KEY:-}" ]] && run_args+=(-e OPENROUTER_API_KEY)
    [[ -n "${LINGOCOACH_TOTP_SECRET:-}" ]] && run_args+=(-e LINGOCOACH_TOTP_SECRET)
    [[ -n "${TOTP_SECRET:-}" ]] && run_args+=(-e TOTP_SECRET)
  fi

  echo "LingoCoach: starting container on ${host}:${PORT}…"
  podman run -d "${run_args[@]}" "$IMAGE"
  health_check
}

install_systemd() {
  local unit_src unit_dir unit_dst env_file="" host publish
  unit_src="$(pwd)/lingocoach.container"
  unit_dir="${HOME}/.config/containers/systemd"
  unit_dst="${unit_dir}/lingocoach.container"
  host="$(bind_host)"
  publish="${host}:${PORT}:8066"

  [[ -f "$unit_src" ]] || {
    echo "Missing ${unit_src}" >&2
    exit 1
  }

  mkdir -p "$unit_dir"
  # Rewrite PublishPort for this host bind; keep other lines from the repo unit.
  awk -v pub="$publish" -v https="$HTTPS" '
    BEGIN { https_set = 0 }
    /^PublishPort=/ { print "PublishPort=" pub; next }
    /^Environment=LINGOCOACH_HTTPS=/ { next }
    /^EnvironmentFile=/ {
      print
      if (https == 1 && https_set == 0) {
        print "Environment=LINGOCOACH_HTTPS=1"
        https_set = 1
      }
      next
    }
    { print }
    END {
      if (https == 1 && https_set == 0) {
        print "Environment=LINGOCOACH_HTTPS=1"
      }
    }
  ' "$unit_src" >"$unit_dst"

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
  # Restart so a previous public bind is replaced with the new PublishPort.
  systemctl --user restart lingocoach.service
  health_check
  echo "LingoCoach: systemd user unit lingocoach.service is active (PublishPort=${publish})."
  echo "  Logs: journalctl --user -u lingocoach.service -f"
}

# --- entry ---
# Fail fast on --https before binding the app to loopback / rewriting units.
if [[ "$HTTPS" -eq 1 ]]; then
  _early_domain="$(resolve_domain)"
  if [[ -z "$_early_domain" ]]; then
    echo "HTTPS requires a real DNS name." >&2
    echo "  Set LINGOCOACH_DOMAIN (preferred), or DOMAIN / VPS_HOST, then re-run with --https." >&2
    echo "  Example: LINGOCOACH_DOMAIN=coach.example.com ./deploy-vps.sh --https" >&2
    exit 1
  fi
  case "$_early_domain" in
    YOUR_DOMAIN_HERE|your.domain.example|example.com|coach.example.com|*.invalid|*placeholder*)
      echo "Refusing placeholder domain '${_early_domain}'. Use your real DNS name." >&2
      exit 1
      ;;
  esac
  unset _early_domain
fi

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

if [[ "$HTTPS" -eq 1 ]]; then
  install_caddy_https
fi
