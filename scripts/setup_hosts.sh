#!/usr/bin/env bash
# Map the private RHOAI demo LLM hostname for local bare-metal runs.
set -euo pipefail

IP="${RHOAI_LLM_IP:-192.168.147.135}"
HOST="${RHOAI_LLM_HOST:-redhataiqwen38-27b-int4-rhoai-test.apps.demo.rhoai.demo}"
LINE="${IP} ${HOST}"

if grep -qE "[[:space:]]${HOST//./\\.}([[:space:]]|$)" /etc/hosts; then
  sudo sed -i -E "s/^.*[[:space:]]${HOST//./\\.}([[:space:]].*)?$/${LINE}/" /etc/hosts
  echo "Updated /etc/hosts: ${LINE}"
else
  echo "${LINE}" | sudo tee -a /etc/hosts >/dev/null
  echo "Added /etc/hosts: ${LINE}"
fi

getent hosts "${HOST}" || true
