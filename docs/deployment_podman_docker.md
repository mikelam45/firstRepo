# Optional: Podman / Docker on the same MacBook

**Preferred run path:** [mac_local_run.md](mac_local_run.md) (`bash scripts/run_local_mac.sh`) — no container required.

This page is only if you want containers **on the same Mac**. Not for VPS or Cursor Cloud.

The screener can run inside a local container, with mail/output bind-mounted and the LLM on your LAN/VPN.

## Quick start

```bash
cp .env.example .env
# Edit MAIL_HOST_PATH if using a real Thunderbird folder
# Edit LLM_BASE_URL for Podman vs Docker (see below)

podman compose up --build
# Docker Desktop / Engine:
docker compose up --build
```

Service listens on **http://127.0.0.1:3036** (`HOST=0.0.0.0`, `PORT=3036`). UI at `/`, health at `/health`, smoke JSON at `/api/smoke`.

Bare-metal (no Podman/Docker):

```bash
pip install -r requirements.txt && pip install -e .
THUNDERBIRD_MAIL_PATH=./fixtures/mbox OUTPUT_DIR=./output/candidate_reviews \
  ROLE_CONFIG_PATH=./config/role_requirements.yaml \
  python3 -m candidate_eval.cli serve --port 3036
```

### Run a keyword-scoped review (scaffold)

```bash
podman compose run --rm screener review --keywords "kubernetes,react,system design,remote"
```

### Interactive shell in the image

```bash
podman compose run --rm screener shell
```

## Host ↔ container map

| Host | Container | Mode |
| --- | --- | --- |
| `$MAIL_HOST_PATH` (default `./fixtures/mbox`) | `/data/mail` | read-only |
| `$OUTPUT_HOST_PATH` (default `./output/candidate_reviews`) | `/data/output` | read-write |
| `./config/role_requirements.yaml` | `/app/config/role_requirements.yaml` | read-only |

Inside the container, `THUNDERBIRD_MAIL_PATH=/data/mail` and `TARGET_MAIL_FOLDER` selects the mbox file name (fixture default: `Applications`).

## LLM: OpenRouter

Configured in `.env` (see [`.env.example`](../.env.example)):

```env
OPENROUTER_API_KEY="sk-or-v1-..."
LLM_API_KEY="sk-or-v1-..."
API_URL="https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME="qwen/qwen3-32b"
```

Smoke/`llm_chat` uses Bearer auth against OpenRouter. No private TLS cert or `/etc/hosts` mapping is required. Keep the real key only in `.env` (gitignored).

For a private OpenAI-compatible host instead, you can still set `API_URL` plus optional `CERT_FILE` / `TOKEN_FILE`.

## SELinux (Podman on Fedora/RHEL)

If mounts fail with permission errors, relabel:

```yaml
- ${MAIL_HOST_PATH}:/data/mail:ro,Z
- ${OUTPUT_HOST_PATH}:/data/output:rw,Z
```

## Real Thunderbird mail

```bash
# macOS example
MAIL_HOST_PATH="$HOME/Library/Thunderbird/Profiles/<id>/Mail/Local Folders"
TARGET_MAIL_FOLDER=INBOX

# Linux example
MAIL_HOST_PATH="$HOME/.thunderbird/<id>/Mail/Local Folders"
```

Export those in `.env` (and set `TARGET_MAIL_FOLDER`) before `compose up`.

## Build without compose

```bash
podman build -t localhost/candidate-eval:local .
podman run --rm \
  --env-file .env \
  --add-host=host.containers.internal:host-gateway \
  -v "$(pwd)/fixtures/mbox:/data/mail:ro" \
  -v "$(pwd)/output/candidate_reviews:/data/output:rw" \
  localhost/candidate-eval:local smoke
```
