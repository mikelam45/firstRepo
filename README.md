# Fieldnote environment

Two machines, two modes.

| Machine | Role | Command |
| --- | --- | --- |
| MacBook | Development at `/Users/mikelam/firstRepo/RAG_portal` | `bash scripts/dev.sh` |
| Linux VPS | Production, after dev is tested | `bash scripts/vps-up.sh` |

The API is a small shell so the environment can be tested before the multimodal portal is built on top of it. Development stores notes in SQLite and leaves writes open on localhost. Production requires `PORTAL_API_TOKEN` on writes and refuses to serve if that token is missing.

## MacBook

Keep this checkout at `/Users/mikelam/firstRepo/RAG_portal`. That folder is the local development copy on the Mac. Do not deploy it to the VPS.

Requires Python 3.12 and git.

```bash
mkdir -p /Users/mikelam/firstRepo
git clone https://github.com/mikelam45/firstRepo.git /Users/mikelam/firstRepo/RAG_portal
cd /Users/mikelam/firstRepo/RAG_portal
bash scripts/dev.sh
```

If `main` does not have these scripts yet, check out the development branch after clone:

```bash
git checkout cursor/multimodal-rag-portal-1e46
```

The first run creates `.venv`, installs `backend/requirements.txt`, and copies `.env.development.example` to `.env.development`. The server listens on `http://127.0.0.1:8099`.

Open that URL in a browser to assign a model to each function. The page lists the provider, model id, a one-line use, and the recorded unit price. It loads without an OpenRouter key. Choices are stored in `data/model-selection.json` (or `$DATA_DIR/model-selection.json`).

`scripts/dev.sh` reads `/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal` when that file is present and `OPENROUTER_API_KEY` is not already set. It exports `OPENROUTER_API_KEY` for uvicorn and does not print the key. The file stays outside this checkout and is not committed. `.gitignore` ignores `.env` files, including a copy named `.env_RAG_portal`, so the key file cannot land in git. The file may contain `OPENROUTER_API_KEY=...`, `OPENROUTER_KEY=...`, or the raw key on one line. Blank lines and comments are ignored. If the file is missing, development still starts and the key stays unset.

The app resolves the key in this order: `OPENROUTER_API_KEY` in the process environment, then the file named by `OPENROUTER_ENV_FILE`, then `/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal`. `GET /api/models` includes `openrouter_configured` (`true` or `false`) and `openrouter_status` (`key_accepted`, `key_rejected`, or `not_configured`). The response never includes the key. When a key is configured, the server sends `GET https://openrouter.ai/api/v1/key` with `Authorization: Bearer` and a short timeout, and reports only that status. The public models list is not used for this check, because it answers without a key. The key endpoint's body can include a shortened label, so the app reads the HTTP status and nothing else. `GET /health` includes `openrouter_configured` and does not call OpenRouter.

```bash
curl http://127.0.0.1:8099/health
curl http://127.0.0.1:8099/api/models
curl -X POST http://127.0.0.1:8099/api/notes -H 'content-type: application/json' -d '{"body":"hello from the mac"}'
```

`GET /api/models` is open in both modes. `PUT /api/models` is open in development. In production it requires `Authorization: Bearer $PORTAL_API_TOKEN`, the same rule as creating a note. The body is the five function keys (`rag_qa`, `translation`, `cantonese_script`, `image_gen`, `video_gen`) mapped to model ids from the catalog.

Tests:

```bash
.venv/bin/pytest backend
```

`scripts/dev.sh` exits if `APP_ENV` is not `development`.

## VPS

Do this only after the Mac tests pass. On the server:

```bash
git clone https://github.com/mikelam45/firstRepo.git
cd firstRepo
cp .env.production.example .env.production
# Edit PORTAL_API_TOKEN. Keep APP_ENV=production.
bash scripts/vps-up.sh
```

Docker Compose binds the API to `127.0.0.1:8000`. Put Caddy or nginx on the VPS for HTTPS, and proxy to that port. Notes data lives in the `fieldnote-data` volume.

`scripts/vps-up.sh` will not start when `APP_ENV=development`, when the token is still the example placeholder, or when Docker is missing.

## Cloud agent

`scripts/cloud-install.sh` is the idempotent install. `scripts/cloud-start.sh` runs the development server on `0.0.0.0:8099` without reload. Neither script reads production secrets. Production on the VPS stays on port 8000.
