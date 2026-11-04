# Fieldnote environment

Two machines, two modes.

| Machine | Role | Command |
| --- | --- | --- |
| MacBook | Development at `/Users/mikelam/firstRepo/RAG_portal` | `bash scripts/dev.sh` |
| Linux VPS | Production, after dev is tested | `bash scripts/vps-up.sh` |

The API is a small shell so the environment can be tested before the multimodal portal is built on top of it. Development stores notes in SQLite and leaves writes open on localhost. Production requires `PORTAL_API_TOKEN` on writes and refuses to serve if that token is missing.

## MacBook

Keep this checkout at `/Users/mikelam/firstRepo/RAG_portal`. That folder is the local development copy on the Mac. Do not deploy it to the VPS.

Requires Python 3.12 or 3.13 (preferred) and git. Python 3.14 works with the pinned FastAPI/pydantic wheels in `backend/requirements.txt`. Homebrew's `python3` on a new Mac is often 3.14; that used to fail because older pydantic-core compiled from source with PyO3, which only supports up to 3.13. `scripts/dev.sh` prefers `python3.12`, then `python3.13`, then `python3`.

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

The first run creates `.venv`, installs `backend/requirements.txt`, and copies `.env.development.example` to `.env.development`. The server listens on `http://127.0.0.1:8099`. A second `scripts/dev.sh` replaces the previous development server on 8099; a foreign process on that port is left alone.

Open `http://127.0.0.1:8099` in Safari or Chrome on this MacBook itself. Cursor Cloud cannot load 127.0.0.1 on the laptop; a link in the cloud chat is the agent VM, not the Mac app. If the page fails on the Mac, run `bash scripts/dev-status.sh` and `lsof -nP -iTCP:8099 -sTCP:LISTEN`.

Open `http://127.0.0.1:8099` for the functions page (RAG chat, translation, Cantonese script, and document upload). LLM setup is at `/setup` (`/settings` is the same page). Setup lists the provider, model id, a one-line use, and the recorded unit price. It loads without an OpenRouter key. Choices are stored in `data/model-selection.json` (or `$DATA_DIR/model-selection.json`). The functions page chats with the saved text model (`rag_qa` by default). Image and video functions are rejected; they are not chat completions.

The recommended Hong Kong default for text functions is DeepSeek (`deepseek/deepseek-chat`). Gemini 2.5 Flash is often blocked in Hong Kong and some other regions. If no `model-selection.json` exists, `GET /api/models` uses DeepSeek for RAG, translation, and Cantonese script. A saved file is left as-is, including a leftover Gemini choice. If chat returns HTTP 403 about region availability, open `/setup` and pick another text model.

`scripts/dev.sh` reads `/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal` when that file is present and `OPENROUTER_API_KEY` is not already set. It exports `OPENROUTER_API_KEY` for uvicorn and does not print the key. The file stays outside this checkout and is not committed. `.gitignore` ignores `.env` files, including a copy named `.env_RAG_portal`, so the key file cannot land in git. The file may contain `OPENROUTER_API_KEY=...`, `OPENROUTER_KEY=...`, or the raw key on one line. Blank lines and comments are ignored. If the file is missing, development still starts and the key stays unset.

The app resolves the key in this order: `OPENROUTER_API_KEY` in the process environment, then the file named by `OPENROUTER_ENV_FILE`, then `/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal`. `GET /api/models` includes `openrouter_configured` (`true` or `false`) and `openrouter_status` (`key_accepted`, `key_rejected`, or `not_configured`). The response never includes the key. When a key is configured, the server sends `GET https://openrouter.ai/api/v1/key` with `Authorization: Bearer` and a short timeout, and reports only that status. The public models list is not used for this check, because it answers without a key. The key endpoint's body can include a shortened label, so the app reads the HTTP status and nothing else. `GET /health` includes `openrouter_configured` and does not call OpenRouter.

The LLM setup page (`/setup`) has an **OpenRouter connection** section above the model picker. It shows the status in plain language and `openrouter_configured`. It does not show the full key. After a save in that browser tab it may show a mask with the last four characters. `POST /api/openrouter/key` with `{ "api_key": "..." }` sets `OPENROUTER_API_KEY` in the server process, writes `OPENROUTER_API_KEY=...` to the Mac env file when that path or its parent exists (mode 0600), or to `$DATA_DIR/openrouter.env` on machines without `/Users/mikelam/firstRepo`, then runs the same key check. An empty body is `400` so a working key is not wiped. `POST /api/openrouter/test` retests the currently loaded key and returns `200` even when the key is rejected. Both POSTs are open in development. In production they require `Authorization: Bearer $PORTAL_API_TOKEN`, the same rule as `PUT /api/models`. Neither response includes the key.

```bash
curl http://127.0.0.1:8099/health
curl http://127.0.0.1:8099/api/models
curl -X POST http://127.0.0.1:8099/api/openrouter/test
curl -X POST http://127.0.0.1:8099/api/notes -H 'content-type: application/json' -d '{"body":"hello from the mac"}'
curl -X POST http://127.0.0.1:8099/api/chat -H 'content-type: application/json' -d '{"message":"hello","function":"rag_qa"}'
curl -F 'file=@notes.csv' http://127.0.0.1:8099/api/rag/files
```

`POST /api/chat` uses the saved model for `rag_qa`, `translation`, or `cantonese_script` (`function` defaults to `rag_qa`). With no OpenRouter key it returns 503, names the Mac file, and does not include a secret. The pages still load. A successful reply includes the model id and the recorded catalog unit price, not a live quote. For `rag_qa`, the request includes extracted text from `$DATA_DIR/uploads/` as context (capped at 80,000 characters, with file names). The model is told to rely on those extracts, not invent file contents, and cite files as `[source: <filename>]`. The JSON reply includes `sources`: `{ id, name, href, excerpt }` for every file that was actually stuffed into the prompt, even when the model omits markers. `href` is `/api/rag/files/{id}/content`. With no uploads, `sources` is `[]` and chat still runs. Translation and Cantonese script do not invent citations. Image and video are never sent to chat completions. The functions page lists those sources under each assistant reply (filename links to the file; excerpt is the first ~160 characters of the extract).

`POST /api/rag/files` accepts `.pdf`, `.docx`, `.doc`, `.txt`, `.md`, `.xlsx`, `.xls`, `.csv`, and `.json` up to 10 MB. Other extensions are `400`. Files are stored under `$DATA_DIR/uploads/` (gitignored). Text extracts go to `$DATA_DIR/extracts/<id>.txt`. The index is `$DATA_DIR/rag-files.json`. `.doc` and `.xls` are stored; extraction notes that they need conversion. A failed PDF extract stores an error and does not crash. `GET /api/rag/files` lists metadata only. `GET /api/rag/files/{id}/content` streams the original upload with `Content-Disposition` and the original filename (`404` if missing). `DELETE /api/rag/files/{id}` removes the file, extract, and index row.

`GET /api/models` and `GET /api/rag/files` are open in both modes. `PUT /api/models`, `POST /api/chat`, `POST /api/openrouter/key`, `POST /api/openrouter/test`, `POST /api/rag/files`, `GET /api/rag/files/{id}/content`, and `DELETE /api/rag/files/{id}` are open in development. In production they require `Authorization: Bearer $PORTAL_API_TOKEN`, the same rule as creating a note. The model-selection body is the five function keys (`rag_qa`, `translation`, `cantonese_script`, `image_gen`, `video_gen`) mapped to model ids from the catalog.

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
