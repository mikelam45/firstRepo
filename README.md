# Candidate Evaluation Framework

Criteria-driven screening for applicant emails/CVs. **Deploy locally with Podman or Docker**: bind-mount Thunderbird/fixtures mail, write scorecards to a host output folder, and call an OpenAI-compatible LLM on the host.

## Local deployment (port **3036**)

HTTP UI + API bind to **http://127.0.0.1:3036** by default.

```bash
cp .env.example .env
# Point MAIL_HOST_PATH at Thunderbird Local Folders or keep ./fixtures/mbox
# Set LLM_BASE_URL for your host LLM

# Podman / Docker (publishes 3036)
podman compose up --build          # or: docker compose up --build

# Bare-metal (no container runtime)
pip install -r requirements.txt && pip install -e .
export THUNDERBIRD_MAIL_PATH=./fixtures/mbox OUTPUT_DIR=./output/candidate_reviews \
  ROLE_CONFIG_PATH=./config/role_requirements.yaml PORT=3036
python3 -m candidate_eval.cli serve --port 3036
```

Open **http://127.0.0.1:3036** — enter review keywords and run. Health: `/health`, smoke: `/api/smoke`.

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
