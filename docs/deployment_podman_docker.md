# Local deployment — Podman / Docker

The screener is intended to run **on your machine inside a container**, with mail and output bind-mounted from the host and the LLM kept outside the container (LM Studio, Ollama, vLLM, etc.).

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

## LLM: CERT_FILE, TOKEN_FILE, API_URL, MODEL_NAME

Configured in `.env` (see [`.env.example`](../.env.example) and [`SSLcert/README.md`](../SSLcert/README.md)):

```env
CERT_FILE="./SSLcert/qwen-tls.crt"
TOKEN_FILE="./SSLcert/token_qwen3_8.txt"
API_URL="https://redhataiqwen38-27b-int4-rhoai-test.apps.demo.rhoai.demo/v1/chat/completions"
MODEL_NAME="Qwen38-27b-int4"
```

### Name resolution

The demo hostname is private. Map it before testing:

```text
192.168.147.135 redhataiqwen38-27b-int4-rhoai-test.apps.demo.rhoai.demo
```

- Podman/Docker: already in [`compose.yml`](../compose.yml) `extra_hosts`
- Bare-metal: `sudo bash scripts/setup_hosts.sh`

Smoke/`llm_chat` uses the cert for TLS verify, reads the bearer token from `TOKEN_FILE`, and POSTs to `API_URL` with `MODEL_NAME`.

For a local OpenAI-compatible host instead, you can still point `API_URL` at that server’s `/v1/chat/completions` and mount/provide cert+token as needed.

`compose.yml` still registers `host.containers.internal` / `host.docker.internal` via `extra_hosts: host-gateway` when the model runs on the host.

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
