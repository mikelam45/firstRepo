# Fieldnote environment

Two machines, two modes.

| Machine | Role | Command |
| --- | --- | --- |
| MacBook | Development | `bash scripts/dev.sh` |
| Linux VPS | Production, after dev is tested | `bash scripts/vps-up.sh` |

The API is a small shell so the environment can be tested before the multimodal portal is built on top of it. Development stores notes in SQLite and leaves writes open on localhost. Production requires `PORTAL_API_TOKEN` on writes and refuses to serve if that token is missing.

## MacBook

Requires Python 3.12.

```bash
bash scripts/dev.sh
```

The first run creates `.venv`, installs `backend/requirements.txt`, and copies `.env.development.example` to `.env.development`. The server listens on `http://127.0.0.1:8000`.

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/notes -H 'content-type: application/json' -d '{"body":"hello from the mac"}'
```

Tests:

```bash
.venv/bin/pytest backend
```

`scripts/dev.sh` exits if `APP_ENV` is not `development`.

## VPS

Do this only after the Mac tests pass. On the server:

```bash
git clone <this-repo>
cd firstRepo
cp .env.production.example .env.production
# Edit PORTAL_API_TOKEN. Keep APP_ENV=production.
bash scripts/vps-up.sh
```

Docker Compose binds the API to `127.0.0.1:8000`. Put Caddy or nginx on the VPS for HTTPS, and proxy to that port. Notes data lives in the `fieldnote-data` volume.

`scripts/vps-up.sh` will not start when `APP_ENV=development`, when the token is still the example placeholder, or when Docker is missing.

## Cloud agent

`scripts/cloud-install.sh` is the idempotent install. `scripts/cloud-start.sh` runs the development server on `0.0.0.0:8000` without reload. Neither script reads production secrets.
