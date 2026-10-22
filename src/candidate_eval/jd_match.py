"""Upload a Job Description and match it against all mailbox candidates."""

from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from candidate_eval.ingest import parse_mbox
from candidate_eval.privacy.guardrail import (
    assert_safe_for_llm,
    build_llm_payload,
    extract_contact_fields,
    redact_text,
)
from candidate_eval.privacy.store import LocalCandidateStore
from candidate_eval.review_pipeline import (
    _db_path,
    _heuristic_score,
    _load_role_config,
    _score_with_llm,
    _tier,
    _weighted_score,
)
from candidate_eval.service import project_root, resolve_repo_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Common role/skill tokens to pull from JD when user does not supply keywords.
_JD_TOKEN_RE = re.compile(
    r"(?i)\b(?:"
    r"kubernetes|k8s|docker|aws|gcp|azure|terraform|ansible|"
    r"python|java|golang|go|typescript|javascript|react|vue|angular|node\.?js|"
    r"system design|microservices|api design|rest|graphql|"
    r"postgresql|mysql|mongodb|redis|kafka|rabbitmq|"
    r"ci/?cd|devops|sre|observability|opentelemetry|"
    r"remote|hybrid|onsite|fintech|saas|backend|frontend|fullstack|"
    r"machine learning|llm|rag|security|compliance"
    r")\b"
)


def parse_jd_bytes(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded JD file."""
    name = (filename or "jd.txt").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            raise ValueError("PDF JD had no extractable text")
        return text
    if name.endswith(".docx"):
        import docx

        document = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in document.paragraphs if p.text.strip()).strip()
        if not text:
            raise ValueError("DOCX JD had no extractable text")
        return text
    # .txt / .md / unknown → utf-8
    return data.decode("utf-8", errors="replace").strip()


def extract_keywords_from_jd(jd_text: str, *, fallback: list[str] | None = None) -> list[str]:
    """Derive review keywords from JD text (case-preserving unique list)."""
    found = _JD_TOKEN_RE.findall(jd_text or "")
    keywords: list[str] = []
    seen: set[str] = set()
    for token in found:
        key = token.lower().replace(".", "")
        if key in seen:
            continue
        seen.add(key)
        keywords.append(token.lower())
    if keywords:
        return keywords
    if fallback:
        return list(fallback)
    role = _load_role_config()
    return list(role.get("review_keywords") or [])


def _match_label(tier: str, knockout_status: str, weighted: float) -> str:
    if knockout_status == "pass" and tier in {"tier_1", "tier_2"}:
        return "matched"
    if knockout_status == "pass" and weighted >= 2.5:
        return "partial"
    return "not_matched"


def _redact_jd_for_llm(jd_text: str) -> tuple[str, list[dict[str, str]]]:
    """JD may contain recruiter emails — redact before any LLM call."""
    sensitive = extract_contact_fields(jd_text, {})
    return redact_text(jd_text, sensitive=sensitive)


def _score_candidate_against_jd(
    *,
    candidate_id: str,
    payload: dict[str, Any],
    jd_redacted: str,
    keywords: list[str],
    min_must: int,
    use_llm: bool,
) -> dict[str, Any]:
    jd_payload = {
        **payload,
        "job_description": jd_redacted,
        "task": (
            "Compare the redacted application_text to the job_description. "
            "Score fit for this JD specifically."
        ),
    }
    assert_safe_for_llm(jd_payload)

    if use_llm:
        try:
            return _score_with_llm(jd_payload)
        except Exception:  # noqa: BLE001
            scorecard = _heuristic_score(payload, keywords, min_must)
            scorecard["flags"] = list(scorecard.get("flags") or []) + [
                "llm_fallback_heuristic",
                "jd_match",
            ]
            return scorecard

    scorecard = _heuristic_score(payload, keywords, min_must)
    # Boost JD title/token overlap into role_alignment heuristic.
    app = (payload.get("application_text") or "").lower()
    jd_lower = jd_redacted.lower()
    jd_tokens = {t for t in re.findall(r"[a-zA-Z]{4,}", jd_lower)}
    app_tokens = {t for t in re.findall(r"[a-zA-Z]{4,}", app)}
    overlap = len(jd_tokens & app_tokens)
    if overlap >= 12:
        scorecard["scores"]["role_alignment"] = max(
            int(scorecard["scores"]["role_alignment"]), 4
        )
    elif overlap >= 6:
        scorecard["scores"]["role_alignment"] = max(
            int(scorecard["scores"]["role_alignment"]), 3
        )
    scorecard["flags"] = list(scorecard.get("flags") or []) + ["jd_match"]
    scorecard["jd_token_overlap"] = overlap
    return scorecard


def match_jd_to_candidates(
    *,
    jd_text: str,
    jd_filename: str | None,
    mbox_path: str | Path,
    output_dir: Path,
    keywords: list[str] | None = None,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    """Match one JD against every candidate in the mbox; return all results."""
    jd_text = (jd_text or "").strip()
    if len(jd_text) < 40:
        raise ValueError("JD text is too short — paste or upload a full job description")

    role_cfg = _load_role_config()
    role_title = (role_cfg.get("role") or {}).get("title") or "Role"
    min_must = int((role_cfg.get("keyword_policy") or {}).get("min_must_match") or 1)
    resolved_keywords = keywords or extract_keywords_from_jd(
        jd_text, fallback=list(role_cfg.get("review_keywords") or [])
    )
    if not resolved_keywords:
        raise ValueError(
            "Could not derive keywords from JD. Provide review keywords explicitly."
        )

    if use_llm is None:
        use_llm = (os.environ.get("REVIEW_USE_LLM", "true") or "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    jd_redacted, jd_redactions = _redact_jd_for_llm(jd_text)
    assert_safe_for_llm(jd_redacted)

    run_id = (
        f"jd_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
        f"{uuid.uuid4().hex[:8]}"
    )
    db_path = _db_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    jd_dir = output_dir / "job_descriptions"
    jd_dir.mkdir(parents=True, exist_ok=True)
    jd_path = jd_dir / f"{run_id}.txt"
    jd_path.write_text(jd_text, encoding="utf-8")

    messages = parse_mbox(mbox_path)
    if not messages:
        raise ValueError(f"No candidates found in mbox: {mbox_path}")

    candidates_out: list[dict[str, Any]] = []
    blocked = 0
    llm_errors: list[str] = []

    with LocalCandidateStore(db_path) as store:
        store.create_run(
            run_id,
            keywords=resolved_keywords,
            mbox_path=str(mbox_path),
        )
        # Persist JD metadata on the run via a sidecar row if schema supports it.
        try:
            store._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_descriptions (
                  run_id TEXT PRIMARY KEY,
                  filename TEXT,
                  jd_path TEXT NOT NULL,
                  jd_text TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
                """
            )
            store._conn.execute(
                """
                INSERT OR REPLACE INTO job_descriptions
                  (run_id, filename, jd_path, jd_text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, jd_filename, str(jd_path), jd_text, _utc_now()),
            )
            store._conn.commit()
        except Exception:  # noqa: BLE001
            pass

        for msg in messages:
            candidate_id = f"cand_{msg['email_hash'][:12]}"
            sensitive = extract_contact_fields(msg["body"], msg["headers"])
            try:
                payload, redactions = build_llm_payload(
                    candidate_id=candidate_id,
                    subject=msg["subject"],
                    body=msg["body"],
                    review_keywords=resolved_keywords,
                    role_title=role_title,
                    sensitive=sensitive,
                )
            except ValueError as exc:
                blocked += 1
                llm_errors.append(f"{candidate_id}: guardrail blocked — {exc}")
                candidates_out.append(
                    {
                        "candidate_id": candidate_id,
                        "name": sensitive.get("name"),
                        "email": sensitive.get("email"),
                        "subject": msg["subject"],
                        "match_status": "blocked",
                        "tier": "tier_3",
                        "weighted_score": 0.0,
                        "knockout_status": "fail",
                        "knockout_reasons": [str(exc)],
                        "keyword_hits": [],
                        "scores": None,
                        "privacy": {"sensitive_stored_locally": True, "redaction_count": 0},
                    }
                )
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
                allowed_payload={**payload, "job_description": jd_redacted},
                redactions=redactions + jd_redactions,
            )

            scorecard = _score_candidate_against_jd(
                candidate_id=candidate_id,
                payload=payload,
                jd_redacted=jd_redacted,
                keywords=resolved_keywords,
                min_must=min_must,
                use_llm=use_llm,
            )

            extracted = dict(scorecard.get("extracted") or {})
            extracted["name"] = sensitive.get("name")
            extracted["email"] = sensitive.get("email")
            extracted["phone"] = sensitive.get("phone")
            extracted["linkedin"] = sensitive.get("linkedin")
            scorecard["extracted"] = extracted
            scorecard["candidate_id"] = candidate_id

            evidence = scorecard.get("keyword_evidence") or []
            present_kws = [e["keyword"] for e in evidence if e.get("present")]
            present = len(present_kws)
            knockout_fail = present < min_must or not sensitive.get("email")
            knockout_reasons = []
            if present < min_must:
                knockout_reasons.append(
                    f"keyword_present {present} < min_must_match {min_must}"
                )
            if not sensitive.get("email"):
                knockout_reasons.append("missing_contact_email")

            weighted = _weighted_score(scorecard.get("scores") or {})
            tier = _tier(weighted, knockout_fail)
            knockout_status = "fail" if knockout_fail else "pass"
            match_status = _match_label(tier, knockout_status, weighted)

            scorecard["weighted_score"] = weighted
            scorecard["tier"] = tier
            scorecard["knockout_status"] = knockout_status
            scorecard["knockout_reasons"] = knockout_reasons
            scorecard["match_status"] = match_status
            scorecard["review_keywords"] = resolved_keywords
            scorecard["privacy"] = {
                "sensitive_stored_locally": True,
                "llm_received_redacted_payload_only": True,
                "jd_redacted_for_llm": True,
                "redaction_count": len(redactions) + len(jd_redactions),
            }
            scorecard["scored_at"] = _utc_now()
            store.save_scorecard(candidate_id, scorecard)

            candidates_out.append(
                {
                    "candidate_id": candidate_id,
                    "name": sensitive.get("name"),
                    "email": sensitive.get("email"),
                    "subject": msg["subject"],
                    "match_status": match_status,
                    "tier": tier,
                    "weighted_score": weighted,
                    "knockout_status": knockout_status,
                    "knockout_reasons": knockout_reasons,
                    "keyword_hits": present_kws,
                    "scores": scorecard.get("scores"),
                    "rationales": scorecard.get("rationales"),
                    "privacy": scorecard["privacy"],
                }
            )

        summary = store.summary(run_id)

    # Sort: matched first, then partial, then not_matched/blocked; score desc.
    order = {"matched": 0, "partial": 1, "not_matched": 2, "blocked": 3}
    candidates_out.sort(
        key=lambda c: (order.get(c["match_status"], 9), -(c.get("weighted_score") or 0))
    )

    matched_count = sum(1 for c in candidates_out if c["match_status"] == "matched")
    partial_count = sum(1 for c in candidates_out if c["match_status"] == "partial")
    not_matched_count = sum(
        1 for c in candidates_out if c["match_status"] in {"not_matched", "blocked"}
    )

    result = {
        "status": "ok",
        "message": (
            f"Matched JD against {len(candidates_out)} candidate(s). "
            "Sensitive PII stays in local SQLite; LLM sees redacted text only."
        ),
        "run_id": run_id,
        "created_at": _utc_now(),
        "jd_filename": jd_filename,
        "jd_path": str(jd_path),
        "jd_preview": jd_text[:400] + ("…" if len(jd_text) > 400 else ""),
        "review_keywords": resolved_keywords,
        "mbox_path": str(mbox_path),
        "local_db_path": str(db_path),
        "privacy_mode": "local_db_plus_llm_redaction",
        "use_llm": use_llm,
        "counts": {
            "total": len(candidates_out),
            "matched": matched_count,
            "partial": partial_count,
            "not_matched": not_matched_count,
            "guardrail_blocked": blocked,
        },
        "candidates": candidates_out,
        "llm_errors": llm_errors,
        "summary": summary,
        "project_root": str(project_root()),
        "output_dir": str(output_dir),
    }
    meta_path = output_dir / f"{run_id}_jd_match.json"
    meta_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["meta_path"] = str(meta_path)
    return result


def resolve_mbox_for_match(
    mail_path: str | None,
    mail_folder: str | None,
) -> str:
    """Resolve a readable mbox file path for JD matching."""
    from candidate_eval.service import load_env, resolve_mail_paths

    load_env()
    mail = resolve_mail_paths(mail_path, mail_folder)
    mbox_path = mail.get("mbox_path") or ""
    if mbox_path and Path(mbox_path).is_file():
        return mbox_path
    candidate = Path(mail.get("mail_path") or "")
    if candidate.is_file():
        return str(candidate)

    fixture = resolve_repo_path("./fixtures/mbox/Applications")
    # Explicit local fixture folder, or mailbox:// without a host-side mbox file.
    if fixture.is_file() and (
        "fixtures/mbox" in (mail_path or mail.get("mail_path") or "")
        or mail.get("scheme") == "mailbox"
        or (os.environ.get("JD_MATCH_USE_FIXTURE", "").strip().lower() in {"1", "true", "yes"})
    ):
        return str(fixture)

    raise ValueError(
        "Readable mbox file required for matching. "
        "Use ./fixtures/mbox with folder Applications for the demo, "
        "or a local Thunderbird mbox file path "
        f"(resolved mbox_path={mbox_path!r})."
    )
