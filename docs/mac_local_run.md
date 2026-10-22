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

## `.env` (OpenRouter only)

```env
OPENROUTER_API_KEY="sk-or-v1-..."
API_URL="https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME="qwen/qwen3-32b"
OPENROUTER_HTTP_REFERER="http://127.0.0.1:3036"
OPENROUTER_APP_TITLE="Candidate Evaluation"
```

No `CERT_FILE`, `TOKEN_FILE`, or other LLM host settings. Portal defaults (host/port/mailbox/DB) come from the app and `scripts/run_local_mac.sh`.

`.env` is gitignored. Never commit the real key.

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

## Browse mailbox folder (Mac)

On the JD match form, next to **Mailbox folder path**, click **Browse…** to open an in-page folder browser (no need to type a long Thunderbird path).

Typical Thunderbird locations:

- `~/Library/Thunderbird/Profiles/<profile>/Mail/<account>/`
- `~/Library/Thunderbird/Profiles/<profile>/ImapMail/<server>/`

Select a **directory** (Use this folder) to fill `mail_path`, or select an **mbox** file (extensionless folder file such as `Applications`) to fill `mail_path` + `mail_folder`. Typed paths still work; Browse is additive.

API (loopback only):

```bash
curl -s 'http://127.0.0.1:3036/api/browse-mail'
curl -s 'http://127.0.0.1:3036/api/browse-mail?path='"$HOME"'/Library/Thunderbird/Profiles'
```

Listing is limited to your home directory and the project root (path traversal outside those roots is rejected).

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
