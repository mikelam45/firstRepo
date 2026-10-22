"""Ingest → local PII store → guardrail → LLM analysis → rehydrate contacts."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from candidate_eval.ingest import parse_mbox
from candidate_eval.privacy.guardrail import (
    assert_safe_for_llm,
    build_llm_payload,
    extract_contact_fields,
)
from candidate_eval.privacy.store import LocalCandidateStore
from candidate_eval.service import llm_chat, project_root, resolve_repo_path


WEIGHTS = {
    "role_alignment": 0.40,
    "career_progression": 0.20,
    "application_quality": 0.10,
    "culture_fit": 0.10,
    "operational_logistics": 0.20,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_role_config() -> dict[str, Any]:
    import os

    raw = os.environ.get("ROLE_CONFIG_PATH", "./config/role_requirements.yaml")
    path = resolve_repo_path(raw, default_rel="./config/role_requirements.yaml")
    if not path.is_file():
        return {"role": {"title": "Role"}, "keyword_policy": {"min_must_match": 1}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _db_path(output_dir: Path) -> Path:
    """Prefer LOCAL_DB_PATH; default to repo data/ so PII is not mixed into OUTPUT_DIR."""
    import os

    del output_dir  # kept for call-site compatibility
    return resolve_repo_path(
        (os.environ.get("LOCAL_DB_PATH") or "").strip() or None,
        default_rel="./data/candidate_eval.sqlite",
    )


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise


def _weighted_score(scores: dict[str, Any]) -> float:
    total = 0.0
    for key, weight in WEIGHTS.items():
        total += weight * float(scores.get(key) or 0)
    return round(total, 4)


def _tier(weighted: float, knockout_fail: bool) -> str:
    if knockout_fail:
        return "tier_3"
    if weighted >= 4.0:
        return "tier_1"
    if weighted >= 3.0:
        return "tier_2"
    return "tier_3"


def _score_with_llm(payload: dict[str, Any]) -> dict[str, Any]:
    """Send only the guardrail-approved payload to the LLM."""
    assert_safe_for_llm(payload)
    system = (
        "You are a hiring screening assistant. Analyze ONLY the provided "
        "application_text. Never invent real emails, phones, or street addresses. "
        "In extracted.name and extracted.email use the provided placeholders "
        "(e.g. [NAME_1], [EMAIL_1]) or null. Return a single JSON object matching "
        "the scorecard schema with keys: candidate_id, scores, rationales, "
        "keyword_evidence, extracted, flags."
    )
    user = (
        "Score this redacted application. Return JSON only.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    assert_safe_for_llm(user)
    response = llm_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    content = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if not content:
        raise ValueError("LLM returned empty content")
    return _extract_json(content)


def _keyword_present(text: str, keyword: str) -> bool:
    """Substring match that ignores clear negations (e.g. 'no kubernetes')."""
    kw = keyword.lower().strip()
    if not kw or kw not in text:
        return False
    for line in text.splitlines():
        if kw not in line:
            continue
        if re.search(
            rf"(?i)\b(?:no|not|without|lacking|never)\b[^\n]{{0,40}}{re.escape(kw)}",
            line,
        ):
            continue
        return True
    return False


def _heuristic_score(
    payload: dict[str, Any],
    keywords: list[str],
    min_must_match: int,
) -> dict[str, Any]:
    """Offline fallback when LLM is unavailable — still uses redacted text only."""
    text = (payload.get("application_text") or "").lower()
    evidence = []
    present_count = 0
    for kw in keywords:
        hit = _keyword_present(text, kw)
        if hit:
            present_count += 1
        evidence.append(
            {
                "keyword": kw,
                "present": hit,
                "strength": 4 if hit else 1,
                "evidence": f"Local keyword scan ({'hit' if hit else 'miss'})",
                "source": "email",
            }
        )
    role = 4 if present_count >= min_must_match else 2
    if present_count == 0:
        role = 1
    scores = {
        "role_alignment": role,
        "career_progression": 3,
        "application_quality": 3 if len(text) > 80 else 2,
        "culture_fit": 3,
        "operational_logistics": 3,
    }
    return {
        "candidate_id": payload["candidate_id"],
        "scores": scores,
        "rationales": {
            "role_alignment": "Heuristic keyword coverage on redacted text.",
            "career_progression": "Heuristic default (LLM skipped).",
            "application_quality": "Heuristic length/clarity proxy.",
            "culture_fit": "Heuristic default (LLM skipped).",
            "operational_logistics": "Heuristic default (LLM skipped).",
        },
        "keyword_evidence": evidence,
        "extracted": {
            "name": payload.get("contact_placeholders", {}).get("name"),
            "email": payload.get("contact_placeholders", {}).get("email"),
            "phone": None,
            "linkedin": None,
            "years_experience": None,
            "current_title": None,
            "current_employer": None,
            "notice_days": None,
            "salary_expectation": None,
            "work_authorization": None,
            "location_model": None,
        },
        "flags": ["heuristic_offline_score"],
    }


def run_privacy_review(
    *,
    keywords: list[str],
    mbox_path: str | Path,
    output_dir: Path,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Full privacy-preserving review for one mbox file."""
    role_cfg = _load_role_config()
    role_title = (role_cfg.get("role") or {}).get("title") or "Role"
    min_must = int((role_cfg.get("keyword_policy") or {}).get("min_must_match") or 1)

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    db_path = _db_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    messages = parse_mbox(mbox_path)
    candidates_out: list[dict[str, Any]] = []
    blocked = 0
    llm_errors: list[str] = []

    with LocalCandidateStore(db_path) as store:
        store.create_run(run_id, keywords=keywords, mbox_path=str(mbox_path))

        for msg in messages:
            candidate_id = f"cand_{msg['email_hash'][:12]}"
            sensitive = extract_contact_fields(msg["body"], msg["headers"])
            try:
                payload, redactions = build_llm_payload(
                    candidate_id=candidate_id,
                    subject=msg["subject"],
                    body=msg["body"],
                    review_keywords=keywords,
                    role_title=role_title,
                    sensitive=sensitive,
                )
            except ValueError as exc:
                blocked += 1
                llm_errors.append(f"{candidate_id}: guardrail blocked — {exc}")
                continue

            store.upsert_candidate(
                candidate_id=candidate_id,
                run_id=run_id,
                message_id=msg["message_id"],
                email_hash=msg["email_hash"],
                sensitive=sensitive,
                subject=msg["subject"],
                raw_headers=msg["headers"],
                raw_body=msg["body"],
                allowed_payload=payload,
                redactions=redactions,
            )

            scorecard: dict[str, Any]
            if use_llm:
                try:
                    scorecard = _score_with_llm(payload)
                except Exception as exc:  # noqa: BLE001
                    llm_errors.append(f"{candidate_id}: LLM error — {exc}")
                    scorecard = _heuristic_score(payload, keywords, min_must)
                    scorecard["flags"] = list(scorecard.get("flags") or []) + [
                        "llm_fallback_heuristic"
                    ]
            else:
                scorecard = _heuristic_score(payload, keywords, min_must)

            # Rehydrate identity from local DB only — never trust LLM for PII.
            extracted = dict(scorecard.get("extracted") or {})
            extracted["name"] = sensitive.get("name")
            extracted["email"] = sensitive.get("email")
            extracted["phone"] = sensitive.get("phone")
            extracted["linkedin"] = sensitive.get("linkedin")
            scorecard["extracted"] = extracted
            scorecard["candidate_id"] = candidate_id

            present = sum(
                1
                for item in (scorecard.get("keyword_evidence") or [])
                if item.get("present")
            )
            knockout_fail = present < min_must or not sensitive.get("email")
            knockout_reasons = []
            if present < min_must:
                knockout_reasons.append(
                    f"keyword_present {present} < min_must_match {min_must}"
                )
            if not sensitive.get("email"):
                knockout_reasons.append("missing_contact_email")

            weighted = _weighted_score(scorecard.get("scores") or {})
            scorecard["weighted_score"] = weighted
            scorecard["tier"] = _tier(weighted, knockout_fail)
            scorecard["knockout_status"] = "fail" if knockout_fail else "pass"
            scorecard["knockout_reasons"] = knockout_reasons
            scorecard["review_keywords"] = keywords
            scorecard["privacy"] = {
                "sensitive_stored_locally": True,
                "llm_received_redacted_payload_only": True,
                "redaction_count": len(redactions),
            }
            scorecard["scored_at"] = _utc_now()

            store.save_scorecard(candidate_id, scorecard)

            # Public summary for UI: no raw body / full headers.
            candidates_out.append(
                {
                    "candidate_id": candidate_id,
                    "name": sensitive.get("name"),
                    "email": sensitive.get("email"),
                    "tier": scorecard["tier"],
                    "weighted_score": weighted,
                    "knockout_status": scorecard["knockout_status"],
                    "knockout_reasons": knockout_reasons,
                    "scores": scorecard.get("scores"),
                    "privacy": scorecard["privacy"],
                }
            )

        summary = store.summary(run_id)

    # Persist run artifact (identity summaries only; full PII remains in SQLite).
    run_meta = {
        "run_id": run_id,
        "created_at": _utc_now(),
        "review_keywords": keywords,
        "mbox_path": str(mbox_path),
        "local_db_path": str(db_path),
        "privacy_mode": "local_db_plus_llm_redaction",
        "candidates": candidates_out,
        "guardrail_blocked": blocked,
        "llm_errors": llm_errors,
        "summary": summary,
        "project_root": str(project_root()),
    }
    meta_path = output_dir / f"{run_id}_meta.json"
    meta_path.write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
    run_meta["meta_path"] = str(meta_path)
    run_meta["status"] = "ok"
    run_meta["message"] = (
        "Sensitive fields stored in local SQLite; only redacted analysis text "
        "was eligible for LLM egress."
    )
    return run_meta
