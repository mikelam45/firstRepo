"""Speaking review. Pronunciation stays unscored. No overall speaking band."""

from __future__ import annotations

import re

from app.phonetics import transcribe

CRITERIA = ("fluency_coherence", "lexical_resource", "grammar_range", "pronunciation")
DENY = (
    "official band",
    "you will score",
    "guaranteed",
    "examiner will give you",
    "你實攞",
    "官方分数",
    "官方分數",
)


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text or "")


def _too_short(part: int, text: str) -> bool:
    count = len(_words(text))
    if part == 1:
        return count < 8
    if part == 2:
        return count < 40
    return count < 15


def _aim(target: float, bands: list[int]) -> float:
    lowest = min(bands) if bands else target
    step = lowest + 0.5
    if step > target:
        step = target
    return float(step)


def review(body: dict) -> dict:
    text = (body.get("learner_text") or "").strip()
    part = int(body.get("part") or 1)
    support = body.get("support") if body.get("support") in {"en", "cmn", "yue"} else "en"
    target_band = float(body.get("target_band") or 6.5)
    speech_ms = body.get("speech_ms")
    short = _too_short(part, text)
    words = _words(text)
    long_words = [word for word in words if len(word) >= 6]
    reuse = long_words[0] if long_words else "example"
    why = {
        "en": f"This practice answer keeps your example and adds the missing step, aiming one step toward {target_band}.",
        "cmn": f"这个练习答案保留了你的例子，并补上缺的一步，朝 {target_band} 靠近半档。",
        "yue": f"呢個練習答案留低你個例子，再補返缺嘅一步，朝 {target_band} 行半級。",
    }[support]
    evidence_fluency = {
        "en": "The answer stays on the question, but pauses were not measured.",
        "cmn": "回答扣题了，但停顿没有被测量。",
        "yue": "答案扣題，但停頓冇量到。",
    }[support]
    evidence_lexis = {
        "en": "A few everyday words carry most of the answer.",
        "cmn": "几个日常词承担了大部分内容。",
        "yue": "幾個日常字詞擔住大部分內容。",
    }[support]
    evidence_grammar = {
        "en": "Most sentences stay short and simple.",
        "cmn": "大多数句子又短又简单。",
        "yue": "大多數句子又短又簡單。",
    }[support]
    practice = (
        f"I taught my {reuse} the skill in small steps, and I felt glad when they could do it alone."
        if part == 2
        else f"I usually cook at home, and yesterday I made a simple meal with {reuse}."
    )
    if short or speech_ms is None and part != 1:
        fluency_status = "unscored"
    elif speech_ms is None:
        fluency_status = "unscored"
    else:
        fluency_status = "partial"
    if short:
        criteria = [
            {"id": name, "status": "unscored", "band": None, "evidence": None}
            for name in CRITERIA
        ]
        findings = [{"type": "too_short"}]
        bands: list[int] = []
    else:
        criteria = [
            {"id": "fluency_coherence", "status": fluency_status, "band": 6 if fluency_status != "unscored" else None, "evidence": evidence_fluency if fluency_status != "unscored" else None},
            {"id": "lexical_resource", "status": "assessed", "band": 6, "evidence": evidence_lexis, "swaps": []},
            {"id": "grammar_range", "status": "assessed", "band": 5, "evidence": evidence_grammar, "upgrade_sentence": f"I explained the steps to my {reuse} because they wanted to manage it alone."},
            {"id": "pronunciation", "status": "unscored", "band": None, "evidence": None},
        ]
        bands = [6, 5]
        findings = []
        if part == 1 and len(words) > 120:
            findings.append({"type": "too_long"})
    bullets = None
    if part == 2:
        bullets = []
        for bullet_id, needle in (("who", "sister"), ("what", "soup"), ("how", "how"), ("why", "because")):
            covered = needle.lower() in text.lower()
            bullets.append({
                "id": bullet_id,
                "covered": covered,
                "quote": needle if covered else None,
            })
            if not covered:
                findings.append({"type": "bullet_missing", "bullet_id": bullet_id})
        for bullet in bullets:
            if bullet["covered"] and bullet["quote"] and bullet["quote"].lower() not in text.lower():
                bullet["covered"] = False
                bullet["quote"] = None
    aim = _aim(target_band, bands) if bands else min(target_band, 6.0)
    phonetic = transcribe(practice, "en", body.get("accent") or "en-GB")
    payload = {
        "contract": "1",
        "criteria": criteria,
        "overall_band": None,
        "overall_hidden_reason": "pronunciation_not_assessed",
        "bullets": bullets,
        "findings": findings,
        "practice_answer": {
            "aim_band": aim,
            "text": practice,
            "why": why[:300],
            "phonetic": phonetic["phonetic"],
        },
        "next_drill": {"part": part, "prompt_id": body.get("prompt_id") or "food-at-home", "focus": "grammar_range" if not short else "fluency_coherence"},
        "safety": {"refused": False},
        "provider": "fixture",
    }
    blob = json_blob(payload)
    if any(word.lower() in blob.lower() for word in DENY):
        raise ValueError("denylist")
    return payload


def json_blob(payload: dict) -> str:
    parts = [payload["practice_answer"]["why"]]
    for row in payload["criteria"]:
        if row.get("evidence"):
            parts.append(row["evidence"])
    return "\n".join(parts)
