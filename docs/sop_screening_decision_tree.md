# SOP: Screening Decision Tree

Standard operating procedure for advancing or declining candidates under the Candidate Evaluation Framework. Aligns with [`candidate_evaluation_framework.md`](candidate_evaluation_framework.md).

## Preconditions

1. `.env` configured; `GET {LLM_BASE_URL}/models` succeeds.
2. `config/role_requirements.yaml` updated for the open role.
3. `review_keywords` non-empty (YAML or `--keywords`).
4. Operator understands rejection send requires human confirmation.

## Decision tree

```text
New message in target mbox
        |
        v
Already in processed_ids.txt? --yes--> Skip (unless --force)
        | no
        v
Parse email + CV attachments
        |
        +--> No contact email ------> Knockout fail --> Tier 3 --> Human gate --> Rejection template
        |
        v
LLM scorecard (scoped to review_keywords)
        |
        v
Keyword present count < min_must_match? --yes--> Knockout fail --> Tier 3
        | no
        v
Other knockout rules fail? --yes--> Tier 3
        | no
        v
Compute weighted_score
        |
        +--> >= 4.00 -----------> Tier 1 --> Interview invite template (manual send)
        |
        +--> 3.00 – 3.99 -------> Tier 2 --> Hold / further screen; optional status_update template
        |
        +--> < 3.00 ------------> Tier 3 --> Human gate --> Rejection template
```

## Human review gate (mandatory for Tier 3)

Before any rejection email leaves the organization:

1. Open `scorecards/<id>.md` and `keyword_evidence`.
2. Confirm knockout reasons are accurate (especially semantic keyword misses).
3. Optionally override tier; record `tier_override_reason`.
4. Set `human_review.confirmed_by`, `confirmed_at`, and `decision` (`reject` | `reopen_tier2` | `reopen_tier1`).
5. Only then copy [`templates/email/rejection.md`](../templates/email/rejection.md) for send.

## Comparative matrix review (Tier 1 / 2)

1. Open `shortlist_matrix.csv` sorted by tier then weighted score.
2. Prefer candidates with higher `keyword_coverage` when scores are within 0.15.
3. Schedule Tier 1 first; keep Tier 2 as backup without sending rejection.

## Escalation

- LLM batch errors (`status: error`): re-run single candidate with `--force` after checking LLM health.
- Suspected bias on culture_fit alone: do not Tier-3 solely on culture_fit; require at least one hard knockout or low `role_alignment` / logistics failure.
