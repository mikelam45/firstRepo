#!/usr/bin/env bash
# Inject RHOAI LLM hostname into a *running* candidate-eval container /etc/hosts.
#
#   bash scripts/add_pod_hosts.sh
#   CONTAINER=candidate-eval bash scripts/add_pod_hosts.sh
#
set -euo pipefail

IP="${RHOAI_LLM_IP:-192.168.147.135}"
HOST="${RHOAI_LLM_HOST:-redhataiqwen38-27b-int4-rhoai-test.apps.demo.rhoai.demo}"
LINE="${IP} ${HOST}"
NAME="${CONTAINER:-candidate-eval}"

runtime=""
if command -v podman >/dev/null 2>&1 && podman inspect "$NAME" >/dev/null 2>&1; then
  runtime=podman
elif command -v docker >/dev/null 2>&1 && docker inspect "$NAME" >/dev/null 2>&1; then
  runtime=docker
else
  echo "FAIL: container '${NAME}' not found via podman or docker."
  echo "Start first: podman compose up -d   # or docker compose up -d"
  echo "Then recreate with DNS baked in: podman compose up -d --force-recreate"
  exit 1
fi

echo "==> Using ${runtime}, container=${NAME}"
echo "==> Adding: ${LINE}"

# Writable /etc/hosts inside the running container (root).
$runtime exec -u 0 "$NAME" sh -c "
  if grep -qE '[[:space:]]${HOST//./\\.}([[:space:]]|\$)' /etc/hosts; then
    sed -i -E 's|^.*[[:space:]]${HOST//./\\.}([[:space:]].*)?\$|${LINE}|' /etc/hosts
    echo updated
  else
    echo '${LINE}' >> /etc/hosts
    echo added
  fi
  grep -E '${HOST//./\\.}' /etc/hosts || true
  getent hosts '${HOST}' || true
"

echo "==> Verify from inside the pod:"
$runtime exec "$NAME" getent hosts "$HOST" || \
  $runtime exec "$NAME" python3 -c "import socket; print(socket.getaddrinfo('${HOST}', 443)[0][4])"

echo "OK: pod can resolve ${HOST} -> ${IP}"
echo "Note: recreate still recommended so compose extra_hosts persist after restart:"
echo "  podman compose up -d --force-recreate"
