# Privacy: local DB + LLM redaction

Sensitive candidate data **never leaves the Mac** in raw form. The review pipeline:

1. Parses a local **filesystem mbox**
2. Stores name / email / phone / LinkedIn / address / raw body in **SQLite** (`LOCAL_DB_PATH`)
3. Builds a **redacted** analysis payload and runs `assert_safe_for_llm`
4. Sends only that payload to the LLM (or scores offline when `REVIEW_USE_LLM=false`)
5. Rehydrates contact fields from the local DB for the UI/scorecard

## Env

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOCAL_DB_PATH` | `./data/candidate_eval.sqlite` | On-disk PII store (gitignored) |
| `REVIEW_USE_LLM` | `true` | `false` → heuristic scoring on redacted text only |

## Mailbox path

Privacy review needs a **real mbox file**. A bare `mailbox://…` URI is not enough — point `THUNDERBIRD_MAIL_PATH` at a local folder (Thunderbird profile or `./fixtures/mbox`) and set `TARGET_MAIL_FOLDER` to the mbox name.

```bash
REVIEW_USE_LLM=false \
THUNDERBIRD_MAIL_PATH=./fixtures/mbox \
TARGET_MAIL_FOLDER=Applications \
python -m candidate_eval.cli review --keywords "kubernetes, system design, remote"
```

## JD match (portal)

Upload or paste a JD at http://127.0.0.1:3036 → **Match all candidates**.  
Every candidate in the mbox is listed (`matched` / `partial` / `not_matched`).  
Demo JD: `fixtures/jd/senior_backend_engineer.txt`.

API: `POST /api/jd-match` (JSON or multipart with `jd_file`).

## What the LLM may see

Allowed: redacted subject/body, redacted JD, keyword list, role title, placeholders like `[EMAIL_1]`.

Forbidden in egress: real emails, phones, LinkedIn URLs, street addresses, government IDs.
