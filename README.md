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

Open that URL in a browser to assign a model to each function. The page lists the provider, model id, a one-line use, and the recorded unit price. It does not call OpenRouter, so it loads without `OPENROUTER_API_KEY`. Choices are stored in `data/model-selection.json` (or `$DATA_DIR/model-selection.json`).

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
