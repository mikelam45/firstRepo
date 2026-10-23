"""Next-drill rule. Deterministic, and never focuses pronunciation in v1."""

from __future__ import annotations

from app.ielts_prompts import prompts_for_part

FOCUS_ORDER = ["grammar_range", "lexical_resource", "fluency_coherence"]


def choose_focus(criteria: list[dict]) -> str:
    pool = []
    for item in criteria:
        if item.get("id") == "pronunciation":
            continue
        if item.get("status") not in {"assessed", "partial"}:
            continue
        if not isinstance(item.get("band"), int):
            continue
        pool.append(item)
    if not pool:
        return "fluency_coherence"
    pool.sort(key=lambda item: (item["band"], FOCUS_ORDER.index(item["id"]) if item["id"] in FOCUS_ORDER else 9))
    return pool[0]["id"]


def next_unused(part: int, prompt_id: str) -> str:
    ids = [item["id"] for item in prompts_for_part(part)]
    if not ids:
        return prompt_id
    if prompt_id not in ids:
        return ids[0]
    index = ids.index(prompt_id)
    return ids[(index + 1) % len(ids)]


def plan_next(part: int, prompt_id: str, criteria: list[dict], findings: list[dict]) -> dict:
    types = {item.get("type") for item in findings}
    if part == 2 and ("bullet_missing" in types or "too_short" in types):
        return {
            "part": 2,
            "prompt_id": prompt_id,
            "focus": "fluency_coherence",
            "checklist": True,
        }
    focus = choose_focus(criteria)
    if "template" in types or "shape" in types:
        return {"part": part, "prompt_id": prompt_id, "focus": focus, "labels": True}
    if "not_english" in types:
        return {"part": part, "prompt_id": prompt_id, "focus": focus, "gloss": True}
    if focus in {"lexical_resource", "grammar_range"}:
        return {"part": part, "prompt_id": prompt_id, "focus": focus}
    return {"part": part, "prompt_id": next_unused(part, prompt_id), "focus": focus}


def aim_band(target_band: float, criteria: list[dict]) -> float:
    assessed = [
        item["band"]
        for item in criteria
        if item.get("id") != "pronunciation"
        and item.get("status") in {"assessed", "partial"}
        and isinstance(item.get("band"), int)
    ]
    if not assessed:
        return min(float(target_band), 6.0)
    return min(float(target_band), float(min(assessed) + 1))
