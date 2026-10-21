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

Default process exits after **smoke** (mounts + keywords + `GET /v1/models`).

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

## Reaching the host LLM

| Runtime | Typical `LLM_BASE_URL` |
| --- | --- |
| Podman | `http://host.containers.internal:1234/v1` |
| Docker Desktop | `http://host.docker.internal:1234/v1` |

`compose.yml` registers both names via `extra_hosts: host-gateway`.

Ensure the LLM server listens on an address the container can reach (binding only to `127.0.0.1` on Linux often blocks containers — bind `0.0.0.0` or use a published port intentionally).

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
