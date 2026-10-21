# Candidate Evaluation Framework

Criteria-driven screening for applicant emails/CVs. **Deploy locally with Podman or Docker**: bind-mount Thunderbird/fixtures mail, write scorecards to a host output folder, and call an OpenAI-compatible LLM on the host.

## Local deployment (Podman / Docker)

```bash
cp .env.example .env
# Point MAIL_HOST_PATH at Thunderbird Local Folders or keep ./fixtures/mbox
# Set LLM_BASE_URL for your host LLM (Podman default: host.containers.internal)

podman compose up --build          # or: docker compose up --build
podman compose run --rm screener review --keywords "kubernetes,react,system design,remote"
```

| File | Purpose |
| --- | --- |
| [`Dockerfile`](Dockerfile) | Local screener image (non-root) |
| [`compose.yml`](compose.yml) | Volumes + `host-gateway` aliases for host LLM |
| [`.env.example`](.env.example) | Container paths, mount overrides, LLM URL |

Default command runs **`smoke`**: checks mail mount, required `review_keywords`, and `GET /models` on the LLM.

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
