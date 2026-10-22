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
### LLM (OpenRouter)

UI loads without calling the model. **Test LLM connectivity** uses OpenRouter:

```env
OPENROUTER_API_KEY="sk-or-v1-..."
API_URL="https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME="qwen/qwen3-32b"
```

Keep the real key only in `.env` (gitignored).

## Configuration (local)

| File | Purpose |
| --- | --- |
| [`.env.example`](.env.example) | Copy to `.env` — Mac paths, OpenRouter key placeholder |
| [`config/role_requirements.yaml`](config/role_requirements.yaml) | Role + `review_keywords` |

```env
HOST=127.0.0.1
PORT=3036
OPENROUTER_API_KEY="sk-or-v1-..."
API_URL="https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME="qwen/qwen3-32b"
```

## Spec & SOP

- [Framework spec](docs/candidate_evaluation_framework.md)
- [Mac local run notes](docs/mac_local_run.md)
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
