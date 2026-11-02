#!/usr/bin/env bash
# Control LingoCoach app systemd unit + status (app health + Caddy).
#
# Usage (from voice-chat/ on the VPS):
#   ./lingocoachctl.sh install|start|stop|restart|status|stop-all
#
# stop      — stop app unit only (Caddy keeps serving; upstream may 502)
# stop-all  — stop app unit and caddy.service
# status    — OK/FAIL for unit, loopback /health, caddy, optional public URL
#
# Never prints secrets from lingocoach.env.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

UNIT_NAME="lingocoach.service"
INTERNAL_PORT="${LINGOCOACH_INTERNAL_PORT:-${INTERNAL_PORT:-18066}}"
HTTPS_PORT="${LINGOCOACH_HTTPS_PORT:-${HTTPS_PORT:-8066}}"
PUBLIC_DOMAIN_DEFAULT="103-195-5-86.as-cloud-xip.com"

# shellcheck source=local-common.sh
. ./local-common.sh

is_root() { [[ "${EUID:-$(id -u)}" -eq 0 ]]; }

# Prefer system unit when root or when /etc unit exists; else user unit.
use_system_unit() {
  if is_root; then
    return 0
  fi
  if [[ -f "/etc/systemd/system/${UNIT_NAME}" ]]; then
    return 0
  fi
  return 1
}

systemctl_app() {
  if use_system_unit; then
    if is_root; then
      systemctl "$@"
    else
      sudo systemctl "$@"
    fi
  else
    systemctl --user "$@"
  fi
}

systemctl_caddy() {
  if is_root || [[ -w /etc/caddy ]]; then
    systemctl "$@"
  else
    sudo systemctl "$@"
  fi
}

resolve_env_file() {
  local candidates=(
    "${LINGOCOACH_ENV_FILE:-}"
    "${HOME}/lingocoach.env"
    "${SCRIPT_DIR}/.env"
  )
  local f
  for f in "${candidates[@]}"; do
    [[ -n "$f" && -f "$f" ]] || continue
    printf '%s' "$f"
    return 0
  done
  printf '%s' "${HOME}/lingocoach.env"
}

resolve_domain() {
  local d="${LINGOCOACH_DOMAIN:-${DOMAIN:-${VPS_HOST:-}}}"
  if [[ -z "$d" ]]; then
    local f line
    f="$(resolve_env_file)"
    if [[ -f "$f" ]]; then
      line="$(grep -E '^[[:space:]]*(export[[:space:]]+)?(LINGOCOACH_DOMAIN|DOMAIN|VPS_HOST)=' "$f" | head -n1 || true)"
      if [[ -n "$line" ]]; then
        d="${line#*=}"
        d="${d#\"}"
        d="${d%\"}"
        d="${d#\'}"
        d="${d%\'}"
      fi
    fi
  fi
  d="${d#"${d%%[![:space:]]*}"}"
  d="${d%"${d##*[![:space:]]}"}"
  d="${d#http://}"
  d="${d#https://}"
  d="${d%%/*}"
  d="${d%%:*}"
  printf '%s' "$d"
}

ensure_venv() {
  echo "LingoCoach: ensuring venv/deps…"
  if ! LINGOCOACH_PREPARE_ONLY=1 ./run-local.sh; then
    echo "LingoCoach: prepare failed (venv/pip)." >&2
    return 1
  fi
}

render_unit() {
  local out="$1"
  local host="${HOST:-127.0.0.1}"
  local port="${PORT:-$INTERNAL_PORT}"
  local https="${LINGOCOACH_HTTPS:-1}"
  local env_file wanted https_env
  env_file="$(resolve_env_file)"
  if use_system_unit || is_root; then
    wanted="multi-user.target"
  else
    wanted="default.target"
  fi
  if [[ "$https" == "1" || "$https" == "true" ]]; then
    https_env="Environment=LINGOCOACH_HTTPS=1"
    host="${HOST:-127.0.0.1}"
    port="${PORT:-$INTERNAL_PORT}"
  else
    https_env="# Environment=LINGOCOACH_HTTPS=1"
    host="${HOST:-0.0.0.0}"
    port="${PORT:-8066}"
  fi

  local content
  content="$(cat "${SCRIPT_DIR}/lingocoach.service")"
  content="${content//__WORKING_DIR__/${SCRIPT_DIR}}"
  content="${content//__ENV_FILE__/${env_file}}"
  content="${content//__HOST__/${host}}"
  content="${content//__PORT__/${port}}"
  content="${content//__HTTPS_ENV__/${https_env}}"
  content="${content//__WANTED_BY__/${wanted}}"
  printf '%s\n' "$content" >"$out"
}

cmd_install() {
  local tmp unit_dst
  ensure_venv

  # Stop leftover nohup/uvicorn so the unit can bind the port.
  PORT="${PORT:-$INTERNAL_PORT}" force_stop_port || true

  tmp="$(mktemp)"
  # shellcheck disable=SC2064
  trap "rm -f '$tmp'" RETURN
  # Default install targets HTTPS loopback (matches ./deploy-vps.sh --https).
  if [[ "${LINGOCOACH_HTTPS:-1}" == "1" || "${LINGOCOACH_HTTPS:-1}" == "true" ]]; then
    LINGOCOACH_HTTPS=1 HOST="${HOST:-127.0.0.1}" PORT="${PORT:-$INTERNAL_PORT}" render_unit "$tmp"
  else
    LINGOCOACH_HTTPS=0 HOST="${HOST:-0.0.0.0}" PORT="${PORT:-8066}" render_unit "$tmp"
  fi

  if use_system_unit || is_root; then
    unit_dst="/etc/systemd/system/${UNIT_NAME}"
    echo "LingoCoach: installing system unit → ${unit_dst}"
    if is_root; then
      cp "$tmp" "$unit_dst"
      systemctl daemon-reload
      systemctl enable --now "$UNIT_NAME"
    else
      sudo cp "$tmp" "$unit_dst"
      sudo systemctl daemon-reload
      sudo systemctl enable --now "$UNIT_NAME"
    fi
    echo "LingoCoach: system unit enabled. Logs: journalctl -u ${UNIT_NAME} -f"
  else
    unit_dst="${HOME}/.config/systemd/user/${UNIT_NAME}"
    echo "LingoCoach: installing user unit → ${unit_dst}"
    mkdir -p "$(dirname "$unit_dst")"
    cp "$tmp" "$unit_dst"
    systemctl --user daemon-reload
    systemctl --user enable --now "$UNIT_NAME"
    if command -v loginctl >/dev/null 2>&1; then
      sudo loginctl enable-linger "$USER" >/dev/null 2>&1 || \
        echo "LingoCoach: enable linger for reboot survival: sudo loginctl enable-linger $USER" >&2
    fi
    echo "LingoCoach: user unit enabled. Logs: journalctl --user -u ${UNIT_NAME} -f"
  fi

  if command -v systemctl >/dev/null 2>&1; then
    if ! systemctl_caddy is-active --quiet caddy 2>/dev/null; then
      echo "LingoCoach: caddy.service is not active. For HTTPS:"
      echo "  cd ${SCRIPT_DIR} && ./deploy-vps.sh --https"
      echo "  # or: sudo systemctl enable --now caddy"
    else
      echo "LingoCoach: caddy.service is active (TLS front-end)."
    fi
  fi
}

cmd_start() {
  ensure_venv
  if ! systemctl_app cat "$UNIT_NAME" >/dev/null 2>&1; then
    echo "LingoCoach: unit not installed; running install…"
    cmd_install
    return 0
  fi
  # Free port from any leftover nohup process before start.
  PORT="${PORT:-$INTERNAL_PORT}" force_stop_port || true
  systemctl_app start "$UNIT_NAME"
  echo "LingoCoach: started ${UNIT_NAME}"
  if ! systemctl_caddy is-active --quiet caddy 2>/dev/null; then
    echo "LingoCoach: remind — enable Caddy for HTTPS: sudo systemctl enable --now caddy"
  fi
}

cmd_stop() {
  if systemctl_app cat "$UNIT_NAME" >/dev/null 2>&1; then
    systemctl_app stop "$UNIT_NAME" || true
    echo "LingoCoach: stopped ${UNIT_NAME} (Caddy left running)."
  else
    echo "LingoCoach: unit not installed; force-stopping listeners on :${INTERNAL_PORT}…"
    PORT="$INTERNAL_PORT" force_stop_port || true
  fi
}

cmd_stop_all() {
  cmd_stop
  if systemctl_caddy cat caddy.service >/dev/null 2>&1; then
    systemctl_caddy stop caddy || true
    echo "LingoCoach: stopped caddy.service"
  else
    echo "LingoCoach: caddy.service not found (nothing to stop)."
  fi
}

cmd_restart() {
  if ! systemctl_app cat "$UNIT_NAME" >/dev/null 2>&1; then
    cmd_install
    return 0
  fi
  systemctl_app restart "$UNIT_NAME"
  echo "LingoCoach: restarted ${UNIT_NAME}"
}

ok_fail() {
  local label="$1" rc="$2"
  if [[ "$rc" -eq 0 ]]; then
    printf '  OK   %s\n' "$label"
  else
    printf '  FAIL %s\n' "$label"
  fi
}

cmd_status() {
  local rc_unit=1 rc_health=1 rc_caddy=1 rc_ext=1
  local domain url
  local overall=0

  echo "LingoCoach status"
  echo "-----------------"

  if systemctl_app is-active --quiet "$UNIT_NAME" 2>/dev/null; then
    rc_unit=0
  fi
  ok_fail "systemd ${UNIT_NAME} active" "$rc_unit"
  [[ "$rc_unit" -eq 0 ]] || overall=1

  if curl -fsS --connect-timeout 3 --max-time 5 \
    "http://127.0.0.1:${INTERNAL_PORT}/health" >/dev/null 2>&1; then
    rc_health=0
  fi
  ok_fail "curl http://127.0.0.1:${INTERNAL_PORT}/health" "$rc_health"
  [[ "$rc_health" -eq 0 ]] || overall=1

  if systemctl_caddy is-active --quiet caddy 2>/dev/null; then
    rc_caddy=0
  fi
  ok_fail "systemd caddy.service active" "$rc_caddy"
  [[ "$rc_caddy" -eq 0 ]] || overall=1

  domain="$(resolve_domain)"
  if [[ -z "$domain" ]]; then
    domain="$PUBLIC_DOMAIN_DEFAULT"
  fi
  url="https://${domain}:${HTTPS_PORT}/health"
  if curl -fsS --connect-timeout 3 --max-time 8 "$url" >/dev/null 2>&1; then
    rc_ext=0
  fi
  ok_fail "curl ${url}" "$rc_ext"
  # External check is informational when cloud firewall blocks; do not fail overall
  # solely on it if loopback + unit + caddy are OK.
  if [[ "$rc_ext" -ne 0 ]]; then
    echo "  note: external HTTPS failed (firewall/DNS/cert). Local checks above matter more for 502."
  fi

  if [[ "$rc_unit" -eq 0 ]]; then
    echo
    systemctl_app --no-pager --full status "$UNIT_NAME" 2>&1 | head -n 12 || true
  fi

  return "$overall"
}

cmd_qr() {
  local base py
  load_totp_env
  base="$(resolve_public_base)"
  py="${SCRIPT_DIR}/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    ensure_venv || return 1
  fi
  if [[ ! -x "$py" ]]; then
    echo "LingoCoach: missing ${py}; run ./lingocoachctl.sh install first." >&2
    return 1
  fi

  echo "LingoCoach: minting one-time Authenticator QR enroll link…"
  echo "  Public base: ${base}"
  echo "  TTL ≈ 20 minutes; single use (first successful page load)."
  # Prints URL + expiry note; never the TOTP secret.
  LINGOCOACH_PUBLIC_BASE="$base" "$py" -m app.totp_qr --base "$base"
}

usage() {
  sed -n '2,13p' "${SCRIPT_DIR}/lingocoachctl.sh"
}

cmd="${1:-}"
case "$cmd" in
  install|enable)
    cmd_install
    ;;
  start)
    cmd_start
    ;;
  stop)
    cmd_stop
    ;;
  stop-all)
    cmd_stop_all
    ;;
  restart)
    cmd_restart
    ;;
  status)
    cmd_status
    ;;
  qr|new-qr)
    cmd_qr
    ;;
  -h|--help|help|"")
    usage
    [[ -n "$cmd" ]] || exit 2
    exit 0
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
