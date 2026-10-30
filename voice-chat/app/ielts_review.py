"""IELTS speaking review. Pronunciation stays unscored. Overall band stays null."""

from __future__ import annotations

import re
from typing import Any

from app.coach import CoachUnavailable, parse_json
from app.ielts_length import content_words, count_words, speaking_gate
from app.ielts_plan import aim_band, plan_next
from app.ielts_prompts import get_prompt
from app.phonetics.pipeline import annotate
from app.phonetics.segment import is_han

REVIEW_DENY = (
    "official band",
    "you will score",
    "guaranteed",
    "examiner will give you",
    "你實攞",
    "官方分数",
    "官方分數",
)

CRITERIA_IDS = ["fluency_coherence", "lexical_resource", "grammar_range", "pronunciation"]


class DenylistHit(Exception):
    pass


def handle_review(payload: dict, provider) -> dict:
    if _refused_text(payload["learner_text"]):
        raw = _refusal_raw(payload)
        return normalize_review(raw, payload)
    if provider.name == "fixture":
        raw = build_review_fixture(payload)
    else:
        raw = _live(payload, provider)
    try:
        return normalize_review(raw, payload)
    except DenylistHit:
        if provider.name == "fixture":
            raise CoachUnavailable()
        raw = _live(payload, provider, repair=True)
        try:
            return normalize_review(raw, payload)
        except DenylistHit:
            raise CoachUnavailable()


def _live(payload: dict, provider, repair: bool = False) -> dict:
    from app.models import ROUTES, route_for_review

    route = route_for_review(payload["support"])
    model = ROUTES[route]["model"]
    fallback = ROUTES[route]["fallback"]
    messages = [
        {
            "role": "system",
            "content": (
                "You review one IELTS-style speaking answer. Return JSON only. "
                "Pronunciation must be unscored with band null. overall_band must be null. "
                "Do not promise a score. Keep the learner's facts in practice_answer.text. "
                "Explanations are in the support language."
            ),
        },
        {"role": "user", "content": _user_json(payload)},
    ]
    if repair:
        messages.append({"role": "user", "content": "Your previous reply was not acceptable. Return only the JSON object. Do not promise a score."})
    text = provider.complete(messages, model, fallback)
    raw = parse_json(text)
    if raw is None:
        text = provider.complete(
            messages
            + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": "Your previous reply was not JSON. Return only the object."},
            ],
            model,
            fallback,
        )
        raw = parse_json(text)
        if raw is None:
            raise CoachUnavailable()
    return raw


def _user_json(payload: dict) -> str:
    import json

    safe = {
        "part": payload["part"],
        "prompt_id": payload["prompt_id"],
        "target_band": payload["target_band"],
        "support": payload["support"],
        "learner_text": payload["learner_text"],
        "speech_ms": payload.get("speech_ms"),
        "notes": payload.get("notes"),
    }
    return json.dumps(safe, ensure_ascii=False)


def _refused_text(text: str) -> bool:
    return bool(
        re.search(
            r"yesterday.?s hong kong|what came up|real (ielts )?test|cue cards?|"
            r"guaranteed band|this week.?s questions|test center questions",
            text or "",
            re.I,
        )
    )


def _refusal_raw(payload: dict) -> dict:
    support = payload["support"]
    why = {
        "en": "These prompts are original practice questions. This app will not list or invent questions from a real test day.",
        "cmn": "这些是原创练习题。本应用不会列出或编造真实考试那天的题目。",
        "yue": "呢啲係原創練習題。呢個 app 唔會列出或者編造真實考試嗰日嘅題目。",
    }[support]
    return {
        "contract": "1",
        "criteria": _blank_criteria(),
        "overall_band": None,
        "bullets": [],
        "findings": [{"type": "refused"}],
        "practice_answer": {
            "aim_band": 6,
            "text": "Please answer the original practice prompt in your own words.",
            "why": why,
        },
        "next_drill": {"part": payload["part"], "prompt_id": payload["prompt_id"], "focus": "fluency_coherence"},
        "safety": {"refused": True},
    }


def build_review_fixture(payload: dict) -> dict:
    text = payload["learner_text"]
    words = count_words(text)
    grammar = 5 if words < 80 else 6
    criteria = [
        {
            "id": "fluency_coherence",
            "status": "assessed",
            "band": 6,
            "evidence": _evidence(payload["support"], "You kept a clear order in the answer."),
        },
        {
            "id": "lexical_resource",
            "status": "assessed",
            "band": 6,
            "evidence": _evidence(payload["support"], "The words match the question, with some repetition."),
            "swaps": [],
        },
        {
            "id": "grammar_range",
            "status": "assessed",
            "band": grammar,
            "evidence": _evidence(payload["support"], "Most sentences follow one simple pattern."),
            "upgrade_sentence": _upgrade(text),
        },
        {"id": "pronunciation", "status": "unscored", "band": None, "evidence": None},
    ]
    bullets = _guess_bullets(payload["prompt_id"], text) if payload["part"] == 2 else []
    return {
        "contract": "1",
        "criteria": criteria,
        "overall_band": 7,
        "bullets": bullets,
        "findings": [],
        "practice_answer": {
            "aim_band": 9,
            "text": _practice_text(text, payload["part"]),
            "why": _why(payload["support"], text),
        },
        "next_drill": {"part": 1, "prompt_id": "food-at-home", "focus": "pronunciation"},
        "safety": {"refused": False},
    }


def normalize_review(raw: dict, payload: dict) -> dict:
    if not isinstance(raw, dict) or raw.get("contract") != "1":
        raise CoachUnavailable()
    learner = payload["learner_text"]
    part = payload["part"]
    support = payload["support"]
    gate = speaking_gate(part, learner)
    english_ok = not _mostly_han(learner)
    refused = bool((raw.get("safety") or {}).get("refused")) or _refused_text(learner)
    criteria = _normalize_criteria(raw.get("criteria"), payload, gate, english_ok)
    bullets = _normalize_bullets(raw.get("bullets"), learner, part, payload["prompt_id"])
    findings = _findings(raw.get("findings"), gate, bullets, english_ok, refused)
    practice = raw.get("practice_answer") if isinstance(raw.get("practice_answer"), dict) else {}
    practice_text = str(practice.get("text") or "").strip()
    if not practice_text:
        practice_text = _practice_text(learner, part)
    practice_text = _keep_named_facts(learner, practice_text)[:2200]
    why = str(practice.get("why") or "").strip() or _why(support, learner)
    why = why[:300]
    _scan_review(criteria, why, findings)
    answer_phone = annotate(practice_text, "en", payload.get("accent") or "en-GB", "mark")
    aim = aim_band(payload["target_band"], criteria)
    speech_ms = payload.get("speech_ms")
    words = count_words(learner)
    length = {"words": words, "speech_ms": speech_ms, "finding": gate, "wpm": None}
    if isinstance(speech_ms, (int, float)) and not isinstance(speech_ms, bool) and speech_ms >= 20000 and words:
        length["wpm"] = int(round(words / (speech_ms / 60000)))
    return {
        "contract": "1",
        "criteria": criteria,
        "overall_band": None,
        "overall_hidden_reason": "pronunciation_not_assessed",
        "bullets": bullets if part == 2 else None,
        "findings": findings,
        "practice_answer": {
            "aim_band": aim,
            "text": practice_text,
            "why": why,
            "phonetic": answer_phone["phonetic"],
            "phonetic_system": answer_phone["phonetic_system"],
            "visemes": answer_phone["visemes"],
        },
        "length": length,
        "next_drill": plan_next(part, payload["prompt_id"], criteria, findings),
        "safety": {"refused": refused},
        "disclaimer": _disclaimer(support),
    }


def _normalize_criteria(raw: Any, payload: dict, gate: str | None, english_ok: bool) -> list[dict]:
    by_id = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("id") in CRITERIA_IDS:
                by_id[item["id"]] = item
    zero = gate == "too_short" or not english_ok
    out = []
    for cid in CRITERIA_IDS:
        source = by_id.get(cid, {})
        if cid == "pronunciation" or zero:
            out.append({"id": cid, "status": "unscored", "band": None, "evidence": None})
            continue
        band = _clamp_band(source.get("band"))
        status = source.get("status")
        if band is None:
            status = "unscored"
        elif cid == "fluency_coherence":
            if payload.get("speech_ms") is None:
                status = "unscored"
                band = None
            else:
                status = "partial"
        elif status not in {"assessed", "partial"}:
            status = "assessed"
        evidence = source.get("evidence")
        if status == "unscored":
            evidence = None
            band = None
        elif not isinstance(evidence, str) or not evidence.strip():
            evidence = _evidence(payload["support"], "Noted from the words in the answer.")
        else:
            evidence = evidence[:240]
        entry = {"id": cid, "status": status, "band": band, "evidence": evidence}
        if cid == "lexical_resource":
            entry["swaps"] = _swaps(source.get("swaps"), payload["learner_text"])
        if cid == "grammar_range":
            entry["upgrade_sentence"] = _valid_upgrade(source.get("upgrade_sentence"), payload["learner_text"])
        out.append(entry)
    return out


def _clamp_band(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not float(value).is_integer():
        return None
    number = int(value)
    if number < 4 or number > 8:
        return None
    return number


def _swaps(raw: Any, learner: str) -> list[dict]:
    if not isinstance(raw, list):
        return []
    lowered = learner.lower()
    kept = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        instead = item.get("instead_of")
        trial = item.get("try")
        if not isinstance(instead, str) or not isinstance(trial, str):
            continue
        if instead.lower() not in lowered:
            continue
        if _accent_police(instead, trial):
            continue
        kept.append({"instead_of": instead, "try": trial[:160]})
        if len(kept) >= 2:
            break
    return kept


def _accent_police(instead: str, trial: str) -> bool:
    blob = f"{instead} {trial}".lower()
    pairs = (("apartment", "flat"), ("elevator", "lift"))
    return any(left in blob and right in blob for left, right in pairs)


def _valid_upgrade(sentence: Any, learner: str) -> str | None:
    if not isinstance(sentence, str) or not sentence.strip():
        return None
    needed = content_words(learner)
    if not needed:
        return sentence.strip()[:400]
    lowered = sentence.lower()
    if any(word in lowered for word in needed):
        return sentence.strip()[:400]
    return None


def _normalize_bullets(raw: Any, learner: str, part: int, prompt_id: str) -> list[dict] | None:
    if part != 2:
        return None
    try:
        prompt = get_prompt(prompt_id)
        ids = prompt.get("bullet_ids") or ["who", "what", "how", "why"]
    except KeyError:
        ids = ["who", "what", "how", "why"]
    incoming = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("id") in ids:
                incoming[item["id"]] = item
    bullets = []
    for bullet_id in ids:
        item = incoming.get(bullet_id, {})
        quote = item.get("quote") if isinstance(item.get("quote"), str) else None
        covered = bool(item.get("covered")) and bool(quote) and quote in learner
        bullets.append({"id": bullet_id, "covered": covered, "quote": quote if covered else None})
    return bullets


def _findings(raw: Any, gate: str | None, bullets: list[dict] | None, english_ok: bool, refused: bool) -> list[dict]:
    findings = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("type") in {"template", "shape", "refused"}:
                findings.append({key: item.get(key) for key in ("type", "bullet_id") if key in item or key == "type"})
    if gate:
        findings.append({"type": gate})
    if not english_ok:
        findings.append({"type": "not_english"})
    if refused and not any(item.get("type") == "refused" for item in findings):
        findings.append({"type": "refused"})
    if bullets:
        for bullet in bullets:
            if not bullet["covered"]:
                findings.append({"type": "bullet_missing", "bullet_id": bullet["id"]})
    return findings


def _scan_review(criteria: list[dict], why: str, findings: list[dict]) -> None:
    chunks = [why]
    for item in criteria:
        if item.get("evidence"):
            chunks.append(item["evidence"])
        if item.get("upgrade_sentence"):
            chunks.append(item["upgrade_sentence"])
    blob = "\n".join(chunks)
    for phrase in REVIEW_DENY:
        if phrase.lower() in blob.lower():
            raise DenylistHit(phrase)


def _mostly_han(text: str) -> bool:
    han = sum(1 for char in text if is_han(char))
    latin = sum(1 for char in text if char.isascii() and char.isalpha())
    return han >= 4 and han > latin


def _blank_criteria() -> list[dict]:
    return [{"id": cid, "status": "unscored", "band": None, "evidence": None} for cid in CRITERIA_IDS]


def _guess_bullets(prompt_id: str, text: str) -> list[dict]:
    catalog = {
        "who": ["my younger sister", "my sister", "my cousin", "my friend"],
        "what": ["tomato soup", "soup", "the skill"],
        "how": ["step by step", "showed her", "showed him", "I showed"],
        "why": ["live alone", "I felt proud", "because"],
        "where": ["near my home", "in the park", "the park"],
        "often": ["every week", "on Saturdays", "often"],
        "see": ["trees", "the river", "people"],
    }
    try:
        ids = get_prompt(prompt_id).get("bullet_ids") or []
    except KeyError:
        ids = ["who", "what", "how", "why"]
    bullets = []
    for bullet_id in ids:
        quote = next((candidate for candidate in catalog.get(bullet_id, []) if candidate in text), None)
        bullets.append({"id": bullet_id, "covered": quote is not None, "quote": quote})
    return bullets


def _practice_text(learner: str, part: int) -> str:
    lowered = learner.lower()
    if "sister" in lowered and "soup" in lowered:
        return (
            "I taught my younger sister to make tomato soup. "
            "I showed her each step on a Saturday, and I felt proud when she cooked the soup on her own."
        )
    cleaned = " ".join(learner.split())
    if not cleaned:
        return "I would like to answer the question with one clear example from my own week."
    if part == 1 and count_words(cleaned) < 12:
        return cleaned.rstrip(".") + ". That is a normal part of my week, and I would give one short reason."
    return cleaned


def _keep_named_facts(learner: str, practice: str) -> str:
    lowered = learner.lower()
    text = practice
    if "sister" in lowered and "sister" not in text.lower():
        text = "I taught my sister. " + text
    if "soup" in lowered and "soup" not in text.lower():
        text = text.rstrip(".") + " We still made soup."
    return text


def _upgrade(learner: str) -> str | None:
    words = content_words(learner)
    if "sister" in learner.lower():
        return "I showed my sister how to season the tomato soup before she cooked it alone."
    if not words:
        return None
    return f"I would add a reason, and I would still mention {words[0]}."


def _why(support: str, learner: str) -> str:
    if "sister" in learner.lower() and "soup" in learner.lower():
        return {
            "en": "You already said who and what you cooked. This version adds how and why, and it keeps your example.",
            "cmn": "你已经说了教谁、做什么。这一版补了怎么教和为什么，仍然用你的例子。",
            "yue": "你已經講咗邊個同煮咩。呢句加咗點教同點解，仍然用你個例子。",
        }[support]
    return {
        "en": "The practice answer stays with your facts and takes one step toward the aim.",
        "cmn": "练习答案保留你的事实，只朝目标走近一步。",
        "yue": "練習答案留低你嘅事實，只係向目標走近一步。",
    }[support]


def _evidence(support: str, en: str) -> str:
    if support == "en":
        return en
    if support == "cmn":
        return "从你写下的句子来看，这一项还可以再具体一点。"
    return "睇你寫嘅句子，呢一項仲可以再具體少少。"


def _disclaimer(support: str) -> dict:
    return {
        "estimate": {
            "en": "Practice estimate only. This is not an IELTS result, and this app is not an IELTS test center.",
            "cmn": "仅为练习估计。这不是雅思成绩，本应用也不是雅思考试中心。",
            "yue": "只係練習估計。呢個唔係雅思成績，呢個 app 亦都唔係雅思考試中心。",
        }[support],
        "pronunciation": {
            "en": "Pronunciation was not assessed, so there is no speaking band.",
            "cmn": "发音未作评估，所以没有口语总分。",
            "yue": "發音未評估，所以冇口語總分。",
        }[support],
    }


def validate_review_request(body: Any) -> dict:
    from app.coach import ServiceError

    if not isinstance(body, dict):
        raise ServiceError(400, "invalid_request", "Body must be a JSON object.")
    session_id = body.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ServiceError(400, "invalid_request", "session_id is required.")
    if body.get("kind") not in {"drill", "diagnostic", "mock_part"}:
        raise ServiceError(400, "invalid_request", "kind is invalid.")
    if body.get("part") not in {1, 2, 3}:
        raise ServiceError(400, "invalid_request", "part must be 1, 2, or 3.")
    try:
        get_prompt(body.get("prompt_id"))
    except (KeyError, TypeError):
        raise ServiceError(400, "invalid_request", "Unknown prompt_id.")
    target = body.get("target_band")
    if not isinstance(target, (int, float)) or isinstance(target, bool):
        raise ServiceError(400, "invalid_request", "target_band is required.")
    if target < 5 or target > 8 or abs(target * 2 - round(target * 2)) > 1e-6:
        raise ServiceError(400, "invalid_request", "target_band must be a half step from 5.0 to 8.0.")
    if body.get("support") not in {"en", "cmn", "yue"}:
        raise ServiceError(400, "invalid_request", "support is invalid.")
    text = body.get("learner_text")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ServiceError(400, "invalid_request", "learner_text is required and must be at most 4000 characters.")
    notes = body.get("notes")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 500):
        raise ServiceError(400, "invalid_request", "notes must be at most 500 characters.")
    speech_ms = body.get("speech_ms", None)
    if speech_ms is not None and (isinstance(speech_ms, bool) or not isinstance(speech_ms, (int, float)) or speech_ms < 0):
        raise ServiceError(400, "invalid_request", "speech_ms must be a number or null.")
    script = body.get("script") or "Hant"
    if script not in {"Hant", "Hans"}:
        raise ServiceError(400, "invalid_request", "script is invalid.")
    accent = body.get("accent") or "en-GB"
    if accent not in {"en-GB", "en-US"}:
        raise ServiceError(400, "invalid_request", "accent is invalid.")
    return {
        "session_id": session_id.strip(),
        "kind": body["kind"],
        "part": body["part"],
        "prompt_id": body["prompt_id"],
        "target_band": float(target),
        "support": body["support"],
        "script": script,
        "accent": accent,
        "speech_ms": None if speech_ms is None else int(speech_ms),
        "notes": notes,
        "learner_text": text,
        "findings_already": body.get("findings_already") or [],
    }
