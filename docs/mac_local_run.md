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
THUNDERBIRD_MAIL_PATH="mailbox://mikelam@systex.com.hk/Inbox/SE_2026"
```

`.env` is gitignored. Never commit the real key.

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
