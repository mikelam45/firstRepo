# Candidate Evaluation Framework

Criteria-driven screening for applicant emails/CVs. **Deploy locally with Podman or Docker**: bind-mount Thunderbird/fixtures mail, write scorecards to a host output folder, and call an OpenAI-compatible LLM on the host.

## Run on your MacBook (port **3036**)

```bash
git clone https://github.com/mikelam45/firstRepo.git
cd firstRepo
git checkout cursor/candidate-eval-spec-65c3

# Place secrets (not in git):
#   SSLcert/qwen-tls.crt
#   SSLcert/token_qwen3_8.txt

bash scripts/run_local_mac.sh
```

Then open **http://127.0.0.1:3036** (health: `/health`, LLM test: UI button or `/api/llm-test`).

The portal UI loads without waiting on the RHOAI LLM (Runtime checks are local config only). Use **Test LLM connectivity** when the model host is reachable (VPN / hosts entry).

### Podman / Docker (optional)

```bash
cp .env.example .env
# add SSLcert secrets, then:
podman compose up --build --force-recreate
# or: docker compose up --build --force-recreate
```

| File | Purpose |
| --- | --- |
| [`Dockerfile`](Dockerfile) / [`compose.yml`](compose.yml) | Image + port `3036:3036`, volumes, host LLM |
| [`.env.example`](.env.example) | `PORT=3036`, mounts, LLM URL |

## Spec & SOP

- **[Framework spec](docs/candidate_evaluation_framework.md)** — scoring, keywords, knockouts, I/O, **§4.1 container deployment**, Phase 4 deferral
- **[Podman/Docker deploy guide](docs/deployment_podman_docker.md)** — mounts, host LLM aliases, SELinux notes
- **[Screening SOP](docs/sop_screening_decision_tree.md)** — operator decision tree + human rejection gate

## Configuration

| File | Purpose |
| --- | --- |
| [`config/role_requirements.yaml`](config/role_requirements.yaml) | Role must-haves, knockouts, **`review_keywords`** |
| [`schemas/scorecard.schema.json`](schemas/scorecard.schema.json) | LLM scorecard JSON contract |

## Templates & fixtures

- Scorecard: [`templates/scorecard/cv_review.md`](templates/scorecard/cv_review.md)
- Emails: [`templates/email/`](templates/email/)
- Sample mbox: [`fixtures/mbox/Applications`](fixtures/mbox/Applications)

## Scoring (summary)

| Dimension | Weight |
| --- | ---: |
| Role Alignment (keyword-scoped) | 40% |
| Career Progression | 20% |
| Application Quality | 10% |
| Culture Fit | 10% |
| Operational Logistics | 20% |

**Tiers:** knockout fail or score &lt; 3.0 → Tier 3; 3.0–3.99 → Tier 2; ≥ 4.0 → Tier 1. Rejection send requires human confirmation.

## Status

Spec, templates, and **local container runtime** (`smoke` + `review` scaffold) are in place. Full ingest→LLM→artifacts pipeline is the next step inside the same image/entrypoint.
