# Candidate Evaluation Framework

**MacBook-only local app** — runs on your machine at **http://127.0.0.1:3036**.  
No VPS, no Cursor Cloud, no remote desktop. Open the URL in Safari/Chrome on the same Mac.

## Run on your MacBook

```bash
git clone https://github.com/mikelam45/firstRepo.git
cd firstRepo
git checkout cursor/candidate-eval-spec-65c3
git pull

# Put OpenRouter key in .env (see .env.example):
#   OPENROUTER_API_KEY=sk-or-v1-...

bash scripts/run_local_mac.sh
```

Leave that Terminal window open, then open:

**http://127.0.0.1:3036**

Health: http://127.0.0.1:3036/health  

Diagnose: `bash scripts/run_local_mac.sh doctor`

### What the script does

- Uses a local Python venv (no cloud)
- Binds the portal to **127.0.0.1:3036** (this Mac only)
- Loads `.env` from the repo root
### JD match (primary UI)

1. Open http://127.0.0.1:3036
2. Upload or paste a job description
3. Point mailbox at `./fixtures/mbox` / `Applications` (demo) or your local mbox
4. Click **Match all candidates** — every candidate is listed with match / partial / not matched

Sensitive contact fields stay in local SQLite (`LOCAL_DB_PATH`); only redacted text is eligible for LLM analysis.

### LLM (OpenRouter)

UI loads without calling the model. **Test LLM connectivity** uses OpenRouter:

`.env` is OpenRouter-only:

```env
OPENROUTER_API_KEY="sk-or-v1-..."
API_URL="https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME="qwen/qwen3-32b"
```

Keep the real key only in `.env` (gitignored). Host/port/mailbox defaults come from the app / Mac runner.

## Configuration (local)

| File | Purpose |
| --- | --- |
| [`.env.example`](.env.example) | Copy to `.env` — OpenRouter key + model only |
| [`config/role_requirements.yaml`](config/role_requirements.yaml) | Role + `review_keywords` |

### Privacy (local DB)

Contact PII is stored only in the Mac-local SQLite DB. The LLM receives redacted text and placeholders. See [docs/privacy_local_db.md](docs/privacy_local_db.md).

Offline dry-run (no LLM call):

```bash
REVIEW_USE_LLM=false \
THUNDERBIRD_MAIL_PATH=./fixtures/mbox \
TARGET_MAIL_FOLDER=Applications \
python -m candidate_eval.cli review --keywords "kubernetes, system design, remote"
```

## Spec & SOP

- [Framework spec](docs/candidate_evaluation_framework.md)
- [Mac local run notes](docs/mac_local_run.md)
- [Privacy / local DB](docs/privacy_local_db.md)
- [Screening SOP](docs/sop_screening_decision_tree.md)

## Scoring (summary)

| Dimension | Weight |
| --- | ---: |
| Role Alignment (keyword-scoped) | 40% |
| Career Progression | 20% |
| Application Quality | 10% |
| Culture Fit | 10% |
| Operational Logistics | 20% |

Tiers: &lt; 3.0 or knockout → Tier 3; 3.0–3.99 → Tier 2; ≥ 4.0 → Tier 1.

## Out of scope

- Hosting on a VPS or public URL  
- Cursor Cloud Agent / Forwarded Ports / Try Live  
- Required Podman/Docker (optional on the same Mac only; see [docs/mac_local_run.md](docs/mac_local_run.md))
