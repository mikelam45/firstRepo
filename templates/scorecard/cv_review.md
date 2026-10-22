# CV Review Scorecard — {{candidate_name}}

| Field | Value |
| --- | --- |
| Candidate ID | {{candidate_id}} |
| Email | {{email}} |
| Role | {{role_title}} |
| Run keywords | {{review_keywords}} |
| Weighted score | {{weighted_score}} / 5 |
| Tier | {{tier}} — {{tier_label}} |
| Knockout | {{knockout_status}} |
| Keyword coverage | {{keyword_coverage}} |
| Model / prompt | {{model}} / {{prompt_version}} |
| Scored at (UTC) | {{scored_at}} |

## Dimension scores

| Dimension | Weight | Score (1–5) | Rationale |
| --- | ---: | ---: | --- |
| Role Alignment | 40% | {{scores.role_alignment}} | {{rationales.role_alignment}} |
| Career Progression | 20% | {{scores.career_progression}} | {{rationales.career_progression}} |
| Application Quality | 10% | {{scores.application_quality}} | {{rationales.application_quality}} |
| Culture Fit | 10% | {{scores.culture_fit}} | {{rationales.culture_fit}} |
| Operational Logistics | 20% | {{scores.operational_logistics}} | {{rationales.operational_logistics}} |

## Keyword evidence

| Keyword | Present | Strength | Source | Evidence |
| --- | --- | ---: | --- | --- |
{{#keyword_evidence}}
| {{keyword}} | {{present}} | {{strength}} | {{source}} | {{evidence}} |
{{/keyword_evidence}}

## Knockout reasons

{{#knockout_reasons}}
- {{.}}
{{/knockout_reasons}}
{{^knockout_reasons}}
- None
{{/knockout_reasons}}

## Extracted logistics

- Years experience: {{extracted.years_experience}}
- Current: {{extracted.current_title}} @ {{extracted.current_employer}}
- Notice (days): {{extracted.notice_days}}
- Salary expectation: {{extracted.salary_expectation}}
- Work authorization: {{extracted.work_authorization}}
- Location model: {{extracted.location_model}}

## Human review gate

- Required: {{human_review.required}}
- Confirmed by: {{human_review.confirmed_by}}
- Confirmed at: {{human_review.confirmed_at}}
- Decision: {{human_review.decision}}
- Tier override reason: {{tier_override_reason}}

_Do not send Tier 3 rejection mail until human review is confirmed._
