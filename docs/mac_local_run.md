# MacBook local run (supported deployment)

This app is intended to run **only on your MacBook**.

| Supported | Not supported |
| --- | --- |
| `bash scripts/run_local_mac.sh` on macOS | VPS / public cloud VM |
| Browser on the same Mac → `http://127.0.0.1:3036` | Cursor Cloud Agent / Forwarded Ports |
| Optional Podman/Docker **on the same Mac** | Remote “Try Live” / desktop control |

## Quick start

```bash
cd /path/to/firstRepo
git checkout cursor/candidate-eval-spec-65c3 && git pull
mkdir -p /Users/mikelam/SSLcert
# place:
#   /Users/mikelam/SSLcert/qwen-tls.crt
#   /Users/mikelam/SSLcert/token_qwen3_8.txt
bash scripts/run_local_mac.sh
```

Open **http://127.0.0.1:3036**. Keep the Terminal session running.

## Secrets layout (absolute)

```text
/Users/mikelam/SSLcert/qwen-tls.crt
/Users/mikelam/SSLcert/token_qwen3_8.txt
```

`.env` values:

```env
HOST=127.0.0.1
PORT=3036
CERT_FILE="/Users/mikelam/SSLcert/qwen-tls.crt"
TOKEN_FILE="/Users/mikelam/SSLcert/token_qwen3_8.txt"
```

## LLM hosts (same Mac)

```bash
sudo bash scripts/setup_hosts.sh
# 192.168.147.135 redhataiqwen38-27b-int4-rhoai-test.apps.demo.rhoai.demo
```

Your Mac must reach `192.168.147.135` (LAN/VPN). The portal UI works even if the LLM is down; use **Test LLM connectivity** when ready.

## Optional: Podman/Docker on the same Mac

Containers are optional and still **local to the Mac** (not a VPS):

```bash
podman compose up --build --force-recreate
# inject hosts into a running local container:
bash scripts/add_pod_hosts.sh
```

Prefer `run_local_mac.sh` unless you specifically want containers.

## Doctor

```bash
bash scripts/run_local_mac.sh doctor
curl http://127.0.0.1:3036/health
```
