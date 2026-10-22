"""Redact sensitive fields before any LLM egress."""

from __future__ import annotations

import re
from typing import Any

# Patterns that must never leave the Mac in LLM payloads.
EMAIL_RE = re.compile(
    r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b"
)
# Require separators or a leading + so salaries like 170000 are not treated as phones.
PHONE_RE = re.compile(
    r"(?<!\d)(?:"
    r"\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}"
    r"|"
    r"\(\d{2,4}\)[\s\-]?\d{3,4}[\s\-]?\d{3,4}"
    r"|"
    r"\d{3}[\s\-.]\d{3}[\s\-.]\d{4}"
    r")(?!\d)"
)
LINKEDIN_RE = re.compile(
    r"(?i)\b(?:https?://)?(?:www\.)?linkedin\.com/in/[a-z0-9\-_%/]+\b"
)
# Passport / national ID–like tokens (conservative).
ID_RE = re.compile(
    r"(?i)\b(?:passport|ssn|national\s*id|hkid|nric)[:\s#]*[A-Z0-9\-]{5,}\b"
)
# Street-ish lines (number + street word).
ADDRESS_RE = re.compile(
    r"(?i)\b\d{1,5}\s+[A-Za-z0-9.'\-]+\s+"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way)\b"
    r"(?:[,\s]+[A-Za-z .]+)?"
)

SENSITIVE_KINDS = ("email", "phone", "linkedin", "id", "address", "name")


def _unique_placeholder(kind: str, index: int) -> str:
    return f"[{kind.upper()}_{index}]"


def extract_contact_fields(text: str, headers: dict[str, str] | None = None) -> dict[str, str | None]:
    """Best-effort local extraction of sensitive contact fields (never sent to LLM raw)."""
    headers = headers or {}
    from_header = headers.get("from") or headers.get("From") or ""
    name = None
    email = None

    m = re.search(r"^(?P<name>[^<]+?)\s*<\s*(?P<email>[^>]+)\s*>$", from_header.strip())
    if m:
        name = m.group("name").strip().strip('"') or None
        email = m.group("email").strip().lower()
    else:
        emails = EMAIL_RE.findall(from_header)
        if emails:
            email = emails[0].lower()

    body_emails = [e.lower() for e in EMAIL_RE.findall(text)]
    if not email and body_emails:
        email = body_emails[0]

    phones = PHONE_RE.findall(text)
    phone = phones[0].strip() if phones else None

    linkedin_hits = LINKEDIN_RE.findall(text)
    linkedin = linkedin_hits[0] if linkedin_hits else None

    address_hits = ADDRESS_RE.findall(text)
    address = address_hits[0].strip() if address_hits else None

    if not name:
        # Last non-empty lines often hold a signature name.
        for line in reversed([ln.strip() for ln in text.splitlines() if ln.strip()]):
            if EMAIL_RE.search(line) or PHONE_RE.search(line):
                continue
            if 1 < len(line.split()) <= 4 and len(line) < 60:
                name = line
                break

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "address": address,
    }


def redact_text(
    text: str,
    *,
    sensitive: dict[str, str | None] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """Replace sensitive tokens with placeholders. Returns (redacted, redaction log)."""
    sensitive = sensitive or {}
    redactions: list[dict[str, str]] = []
    out = text
    counters: dict[str, int] = {k: 0 for k in SENSITIVE_KINDS}

    # Longest explicit values first so names containing substrings redact cleanly.
    explicit: list[tuple[str, str]] = []
    for kind in ("name", "email", "phone", "linkedin", "address"):
        value = (sensitive.get(kind) or "").strip()
        if value:
            explicit.append((kind, value))
    explicit.sort(key=lambda item: len(item[1]), reverse=True)

    for kind, value in explicit:
        if value and value in out:
            counters[kind] += 1
            placeholder = _unique_placeholder(kind, counters[kind])
            out = out.replace(value, placeholder)
            redactions.append(
                {"kind": kind, "original": value, "placeholder": placeholder}
            )

    pattern_specs = (
        ("email", EMAIL_RE),
        ("linkedin", LINKEDIN_RE),
        ("id", ID_RE),
        ("address", ADDRESS_RE),
        ("phone", PHONE_RE),
    )
    for kind, pattern in pattern_specs:
        def _sub(match: re.Match[str], _kind: str = kind) -> str:
            original = match.group(0)
            counters[_kind] += 1
            placeholder = _unique_placeholder(_kind, counters[_kind])
            redactions.append(
                {"kind": _kind, "original": original, "placeholder": placeholder}
            )
            return placeholder

        out = pattern.sub(_sub, out)

    return out, redactions


def assert_safe_for_llm(payload: dict[str, Any] | str) -> None:
    """Hard gate: refuse egress if residual PII patterns remain."""
    blob = payload if isinstance(payload, str) else json_dumps_stable(payload)
    problems: list[str] = []
    if EMAIL_RE.search(blob):
        problems.append("email")
    if LINKEDIN_RE.search(blob):
        problems.append("linkedin")
    if ID_RE.search(blob):
        problems.append("id")
    # Phones are noisier; only fail if an explicit digit run looks like a phone
    # and is not already a placeholder context — check remaining phone-like tokens
    # that are not inside [PHONE_n].
    scrubbed = re.sub(r"\[PHONE_\d+\]", "", blob)
    if PHONE_RE.search(scrubbed):
        problems.append("phone")
    if problems:
        raise ValueError(
            "Guardrail blocked LLM egress; residual sensitive patterns: "
            + ", ".join(problems)
        )


def json_dumps_stable(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def build_llm_payload(
    *,
    candidate_id: str,
    subject: str,
    body: str,
    review_keywords: list[str],
    role_title: str,
    sensitive: dict[str, str | None],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Build the only payload allowed to leave the Mac for analysis."""
    redacted_subject, r1 = redact_text(subject or "", sensitive=sensitive)
    redacted_body, r2 = redact_text(body or "", sensitive=sensitive)
    redactions = r1 + r2

    payload = {
        "candidate_id": candidate_id,
        "review_keywords": review_keywords,
        "role_title": role_title,
        "analysis_scope": (
            "Score skills, experience, application quality, culture signals, "
            "and logistics. Contact identity is withheld; use placeholders only."
        ),
        "subject": redacted_subject,
        "application_text": redacted_body,
        "contact_placeholders": {
            "name": "[NAME_1]" if sensitive.get("name") else None,
            "email": "[EMAIL_1]" if sensitive.get("email") else None,
            "phone": "[PHONE_1]" if sensitive.get("phone") else None,
        },
        "allowed_extracted_fields": [
            "years_experience",
            "current_title",
            "current_employer",
            "notice_days",
            "salary_expectation",
            "work_authorization",
            "location_model",
        ],
        "forbidden_in_response": [
            "real_email",
            "real_phone",
            "street_address",
            "government_id",
        ],
    }
    assert_safe_for_llm(payload)
    return payload, redactions
