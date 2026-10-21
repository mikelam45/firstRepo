# Candidate Evaluation Framework

Criteria-driven screening workflow for applicant emails/CVs: Thunderbird **mbox** ingest, keyword-scoped local LLM scoring, weighted tiers, and human-gated rejection.

## Spec & SOP

- **[Framework spec](docs/candidate_evaluation_framework.md)** — goals, unified scoring, keywords, knockouts, I/O contracts, LLM schema, Phase 4 deferral
- **[Screening SOP / decision tree](docs/sop_screening_decision_tree.md)** — operator steps and human review gate

## Configuration

| File | Purpose |
| --- | --- |
| [`.env.example`](.env.example) | Thunderbird path, LLM endpoint, pipeline settings |
| [`config/role_requirements.yaml`](config/role_requirements.yaml) | Role must-haves, knockouts, **`review_keywords`** |
| [`schemas/scorecard.schema.json`](schemas/scorecard.schema.json) | LLM scorecard JSON contract |

Copy env template:

```bash
cp .env.example .env
```

Override keywords for one run (when the processor exists):

```bash
python review_candidates.py --keywords "kubernetes,react,system design,remote"
```

## Templates

- Scorecard: [`templates/scorecard/cv_review.md`](templates/scorecard/cv_review.md)
- Emails: [`templates/email/`](templates/email/) (invite, status update, rejection)

## Fixtures

Sample mbox: [`fixtures/mbox/Applications`](fixtures/mbox/Applications) (strong + weak applicants for keyword knockout tests).

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

Specification and templates are complete. Pipeline script `review_candidates.py` is the next implementation step (see spec §11).
