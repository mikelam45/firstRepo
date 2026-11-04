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

Open `http://127.0.0.1:8099` for the functions page (RAG chat, translation, Cantonese script, DSE Math assistant, document upload, and Image and storyboard). LLM setup is at `/setup` (`/settings` is the same page). Setup lists the provider, model id, a one-line use, and the recorded unit price. It loads without an OpenRouter key. Choices are stored in `data/model-selection.json` (or `$DATA_DIR/model-selection.json`). The functions page chats with the saved text model (`rag_qa` by default). DSE Math uses the saved `dse_math` text model (`deepseek/deepseek-chat` by default), never Gemini and never the image/video APIs. A photo of a question is read with `POST /api/dse/ocr` as a vision chat completion (`qwen/qwen2.5-vl-72b-instruct` by default), not the Images API. Image and storyboard uses `POST /api/images/generate` against OpenRouter's Images API (`https://openrouter.ai/api/v1/images`) with the saved Hong Kong-safe `image_gen` model (`black-forest-labs/flux.2-pro`). Image and video are never sent to chat completions.

Models that are not available in Hong Kong are omitted from `/setup` and `/` and from `GET /api/models` `functions[].options`. Google Gemini text and image ids stay out of the picker. Defaults are Hong Kong-safe (`deepseek/deepseek-chat` for text, FLUX.2 Pro for image). A leftover saved Gemini choice is coerced to the first Hong Kong-available option for that function so the UI never displays it. If an OpenRouter key is configured, the server probes catalog ids and also hides any that 403 on region. The key is never printed.

`scripts/dev.sh` reads `/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal` when that file is present and `OPENROUTER_API_KEY` is not already set. It exports `OPENROUTER_API_KEY` for uvicorn and does not print the key. The file stays outside this checkout and is not committed. `.gitignore` ignores `.env` files, including a copy named `.env_RAG_portal`, so the key file cannot land in git. The file may contain `OPENROUTER_API_KEY=...`, `OPENROUTER_KEY=...`, or the raw key on one line. Blank lines and comments are ignored. If the file is missing, development still starts and the key stays unset.

The app resolves the key in this order: `OPENROUTER_API_KEY` in the process environment, then the file named by `OPENROUTER_ENV_FILE`, then `/Users/mikelam/firstRepo/openrouter_key/.env_RAG_portal`. `GET /api/models` includes `openrouter_configured` (`true` or `false`) and `openrouter_status` (`key_accepted`, `key_rejected`, or `not_configured`). The response never includes the key. When a key is configured, the server sends `GET https://openrouter.ai/api/v1/key` with `Authorization: Bearer` and a short timeout, and reports only that status. The public models list is not used for this check, because it answers without a key. The key endpoint's body can include a shortened label, so the app reads the HTTP status and nothing else. `GET /health` includes `openrouter_configured` and does not call OpenRouter.

The LLM setup page (`/setup`) has an **OpenRouter connection** section above the model picker. It shows the status in plain language and `openrouter_configured`. It does not show the full key. After a save in that browser tab it may show a mask with the last four characters. `POST /api/openrouter/key` with `{ "api_key": "..." }` sets `OPENROUTER_API_KEY` in the server process, writes `OPENROUTER_API_KEY=...` to the Mac env file when that path or its parent exists (mode 0600), or to `$DATA_DIR/openrouter.env` on machines without `/Users/mikelam/firstRepo`, then runs the same key check. An empty body is `400` so a working key is not wiped. `POST /api/openrouter/test` retests the currently loaded key and returns `200` even when the key is rejected. Both POSTs are open in development. In production they require `Authorization: Bearer $PORTAL_API_TOKEN`, the same rule as `PUT /api/models`. Neither response includes the key.

```bash
curl http://127.0.0.1:8099/health
curl http://127.0.0.1:8099/api/models
curl -X POST http://127.0.0.1:8099/api/openrouter/test
curl -X POST http://127.0.0.1:8099/api/notes -H 'content-type: application/json' -d '{"body":"hello from the mac"}'
curl -X POST http://127.0.0.1:8099/api/chat -H 'content-type: application/json' -d '{"message":"hello","function":"rag_qa"}'
curl -X POST http://127.0.0.1:8099/api/chat -H 'content-type: application/json' -d '{"message":"Solve x^2-5x+6=0","function":"dse_math","target_language":"zh_hk","mode":"practice"}'
curl -F 'file=@question.png' http://127.0.0.1:8099/api/dse/ocr
curl -F 'file=@notes.csv' http://127.0.0.1:8099/api/rag/files
curl -F 'file=@syllabus.txt' http://127.0.0.1:8099/api/dse/files
```

`POST /api/chat` uses the saved model for `rag_qa`, `translation`, `cantonese_script`, or `dse_math` (`function` defaults to `rag_qa`). Optional `grounding` is `mixed` (default) or `strict`; any other value is `400`. The JSON reply echoes `grounding`. Mixed prefers uploaded extracts and may add general knowledge (labeled as not from the documents). Strict answers only from those extracts. With no uploads, mixed still chats and says no documents were uploaded; strict returns `200` with a canned reply and does not call OpenRouter. With no OpenRouter key (except that strict empty-library path) it returns 503, names the Mac file, and does not include a secret. The pages still load. A successful reply includes the model id and the recorded catalog unit price, not a live quote. For `rag_qa`, the request includes extracted text from `$DATA_DIR/uploads/` as context (capped at 80,000 characters, with file names). The model is told to rely on those extracts, not invent file contents, and cite files as `[source: <filename>]`. The JSON reply includes `sources`: `{ id, name, href, excerpt }` for every file that was actually stuffed into the prompt, even when the model omits markers. `href` is `/api/rag/files/{id}/content`. With no uploads, `sources` is `[]`. RAG only stuffs `collection=rag` files.

Translation requires `target_language`: `en` (English), `zh_cn` (Simplified Chinese 简体), or `zh_hk` (Traditional Chinese 繁體). Optional `source_language` is `auto` (default) or the same codes. Missing or invalid language is `400`. The translator prompt asks for the target language only (except proper nouns); 繁體 must not become 简体; 简体 must not use 粵文 particles unless asked; English must be natural. Translation stuffs `collection=translation` extracts the same way RAG does (80k cap) and returns those files in `sources` with the same content download hrefs. RAG files are not mixed in. After a successful translation of uploaded documents, the JSON also includes `artifacts`: `{ id, name, href, source_name }` for a repacked sibling of the same type (`.pdf` → translated PDF with an embedded CJK font when available; `.docx`/`.pptx` replace paragraph or shape text; `.xlsx` cell strings; `.txt`/`.md` as text). Filenames are `{stem}.{target}{suffix}`, stored under `$DATA_DIR/translated/` (gitignored) and recorded as `translated_path` / `translated_href` on the translation file. `GET /api/rag/files/{id}/translated` (alias `GET /api/translation/files/{id}/download`) streams that file with `Content-Disposition` (`404` if it has not been built). RAG chats do not return translated artifacts. An empty message is allowed when translation documents are uploaded; it defaults to `Translate the uploaded documents.` Cantonese script does not invent citations. DSE Math assistant (`function: dse_math`, also `POST /api/dse/ask`) is an HKDSE Mathematics tutor: bilingual `en` / `zh_cn` / `zh_hk` (繁體 stays 繁體), Practice or Explain, optional topic / difficulty / paper / module, strict vs mixed grounding over `collection=dse_math` uploads, step-by-step working, a marked final answer, and `sources` with the same download hrefs as RAG. Replies use the existing table/chart HTML formatter. Strict with no syllabus/notes returns a canned 200 and skips OpenRouter. `POST /api/dse/ocr` accepts one jpeg/png/webp/heic photo (10 MB), stores it under `$DATA_DIR/dse-ocr/` (gitignored, not `collection=dse_math`), and sends it to OpenRouter as a vision chat completion (`https://openrouter.ai/api/v1/chat/completions` with an `image_url` data URI). It does not use `/api/v1/images` or the FLUX `image_gen` path. The default vision model is `qwen/qwen2.5-vl-72b-instruct` (Hong Kong-available in 2026). If that model 403s on region, the server tries another non-Gemini vision id (`qwen/qwen3-vl-8b-instruct`, then `qwen/qwen3-vl-30b-a3b-instruct`, then `anthropic/claude-sonnet-5.5`). Google Gemini ids are not used. The JSON is `{ text, model_id }` (optional `confidence`) and never includes the key. Missing key is 503. Bad type or size is 400. The DSE Math tab has **Read question from photo**; OCR text replaces an empty question box or appends after a blank line. This slice is not the full design: no 3-tier Socratic lock, no DeepSeek-R1 JSON schema, no PostgreSQL mastery tables, no teacher dashboard. Image generation and video jobs are never sent to chat completions. Image generation posts to `https://openrouter.ai/api/v1/images` with the saved `image_gen` model, `prompt`, `n`, `aspect_ratio` (from portal `resolution` or width/height), `output_format` (`png` or `jpeg`; `webp` is requested as png and converted with Pillow), and optional `input_references`. FLUX.2 Pro does not accept a `size` field. Timeout is 120 seconds. Guided fields assemble in this order, empty lines omitted: `subject`, `setting`, `background`, `background_attributes` (Attributes of background), `objects`, `object_attributes` (Attributes of objects), `style` (cinematic still, product photo, storyboard frame, ink wash, documentary), camera/framing, lighting, and extra notes. The assembled prompt is shown before generate. The API accepts those structured fields. Optional `frames` of 1, 4, 6, or 8 beats makes a storyboard (one Images API call per frame). Width and height max out at 2048; presets are 1024x1024, 1024x768, 768x1024, 1344x768, and 1920x1080. Files are stored under `$DATA_DIR/images/` (gitignored). The index is `$DATA_DIR/image-jobs.json`. `GET /api/images` lists jobs with download hrefs; `GET /api/images/{id}/file` streams the original-format file. `POST /api/prompt/enhance` rewrites a prompt with a Hong Kong text model (DeepSeek by default) through chat completions and returns `{ enhanced_prompt }`. A missing OpenRouter key is 503, like chat. A provider region 403 is surfaced; Gemini image is not offered. The functions page keeps the last RAG grounding choice and the last translation target language in `localStorage`, sends them with each chat, lists sources under each assistant reply (filename links to the file; excerpt is the first ~160 characters of the extract), lists Download translated PDF/Word/PPT links from `artifacts`, and shows the grounding mode on RAG assistant bubbles.

`POST /api/rag/files` accepts `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.txt`, `.md`, `.xlsx`, `.xls`, `.csv`, and `.json` up to 10 MB. Other extensions are `400`. Query `?collection=rag` (default), `translation`, or `dse_math` tags the library. `GET/POST /api/translation/files` is the same store with `collection=translation` (translation also accepts `.txt`/`.md` and the Office types above, without `.csv`/`.json`). `GET/POST/DELETE /api/dse/files` is the same store with `collection=dse_math` (same extensions as RAG). Files are stored under `$DATA_DIR/uploads/` (gitignored). Text extracts go to `$DATA_DIR/extracts/<id>.txt`. The index is `$DATA_DIR/rag-files.json`. `.pptx` slide text is extracted. `.doc`, `.xls`, and `.ppt` are stored; extraction notes that they need conversion. A failed PDF extract stores an error and does not crash. `GET /api/rag/files` lists metadata only for the requested collection (`rag` by default). `GET /api/rag/files/{id}/content` streams the original upload with `Content-Disposition` and the original filename (`404` if missing). `DELETE /api/rag/files/{id}` (or `DELETE /api/translation/files/{id}` or `DELETE /api/dse/files/{id}`) removes the file, extract, and index row.

`POST /api/images/references` stores up to 5 jpeg/png/webp files (10 MB each) under `$DATA_DIR/image-refs/` (gitignored). A sixth upload is `400`. `GET /api/images/references` lists them; `DELETE /api/images/references/{id}` removes one. Generate accepts `reference_ids` (max 5). Those become OpenRouter/FLUX.2 Pro `input_references`: `{ "type": "image_url", "image_url": { "url": "<https or data URL>" } }`. Portal `resolution` maps to `aspect_ratio`; portal `format` maps to `output_format`. Image jobs never use `/api/v1/chat/completions`.

`GET /api/models`, `GET /api/rag/files`, `GET /api/dse/files`, `GET /api/images`, and `GET /api/images/references` are open in both modes. `PUT /api/models`, `POST /api/chat`, `POST /api/dse/ask`, `POST /api/dse/ocr`, `POST /api/openrouter/key`, `POST /api/openrouter/test`, `POST /api/rag/files`, `POST /api/translation/files`, `POST /api/dse/files`, `GET /api/rag/files/{id}/content`, `GET /api/rag/files/{id}/translated`, `GET /api/translation/files/{id}/download`, `DELETE /api/rag/files/{id}`, `DELETE /api/dse/files/{id}`, `POST /api/images/generate`, `POST /api/prompt/enhance`, `GET /api/images/{id}/file`, `POST /api/images/references`, `GET /api/images/references/{id}`, and `DELETE /api/images/references/{id}` are open in development. In production they require `Authorization: Bearer $PORTAL_API_TOKEN`, the same rule as creating a note. The model-selection body is the function keys (`rag_qa`, `translation`, `cantonese_script`, `dse_math`, `image_gen`, `video_gen`) mapped to model ids from the catalog.

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
