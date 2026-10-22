# MacBook local run

This app is intended to run **only on your MacBook** at `http://127.0.0.1:3036`.

## Quick start

```bash
cd /Users/mikelam/firstRepo
cp -n .env.example .env   # if needed
# Edit .env and set OPENROUTER_API_KEY
bash scripts/run_local_mac.sh
```

Open: [http://127.0.0.1:3036](http://127.0.0.1:3036)

## Required `.env` (OpenRouter)

```env
HOST=127.0.0.1
PORT=3036
OPENROUTER_API_KEY="sk-or-v1-..."
LLM_API_KEY="sk-or-v1-..."
API_URL="https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME="qwen/qwen3-32b"
LOCAL_DB_PATH="./data/candidate_eval.sqlite"
REVIEW_USE_LLM=true
# Privacy review needs a filesystem mbox (not a bare mailbox:// URI):
THUNDERBIRD_MAIL_PATH="./fixtures/mbox"
TARGET_MAIL_FOLDER="Applications"
# Do not set CERT_FILE or TOKEN_FILE for OpenRouter.
```

OpenRouter uses system CAs (`verify=True`) and `OPENROUTER_API_KEY`. Leave `CERT_FILE` / `TOKEN_FILE` unset (those are only for private RHOAI-style hosts).

`.env` is gitignored. Never commit the real key. SQLite under `data/` is also gitignored.

## Privacy

Sensitive fields (email, phone, LinkedIn, address, raw bodies) stay in `LOCAL_DB_PATH`.  
Only redacted payloads pass the guardrail to the LLM. Details: [privacy_local_db.md](privacy_local_db.md).

Heuristic dry-run (no OpenRouter call):

```bash
source .venv/bin/activate
REVIEW_USE_LLM=false \
THUNDERBIRD_MAIL_PATH=./fixtures/mbox \
TARGET_MAIL_FOLDER=Applications \
python -m candidate_eval.cli review --keywords "kubernetes, system design, remote"
```

The JD match results panel shows run id, local DB path, and per-candidate privacy flags.

## Doctor

```bash
bash scripts/run_local_mac.sh doctor
```

## LLM test

Use **Test LLM connectivity** in the UI, or:

```bash
source .venv/bin/activate
python -m candidate_eval.cli llm-test
```
