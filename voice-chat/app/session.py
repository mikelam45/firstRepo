"""Daily session helpers: level caps, signal union, reset confirm."""

from __future__ import annotations

LEVEL_CAPS = {"beginner": 8, "intermediate": 12, "advanced": 12}
LEVEL_BUDGETS = {"beginner": 1, "intermediate": 2, "advanced": 2}

CORRECTION_PRIORITY = ["mismatch", "completeness", "register", "grammar", "vocabulary", "phrase"]


def learner_count(history: list[dict]) -> int:
    return sum(1 for item in history if item.get("role") == "learner")


def turns_remaining(level: str, history: list[dict]) -> int:
    return max(0, LEVEL_CAPS[level] - learner_count(history))


def turns_remaining_including_this(level: str, history: list[dict]) -> int:
    """Turns left including the learner line already in history. 1 means close."""
    if learner_count(history) == 0:
        return LEVEL_CAPS[level]
    return max(0, LEVEL_CAPS[level] - learner_count(history) + 1)


def needs_reset_confirm(history: list[dict]) -> bool:
    return any(
        item.get("role") == "learner" and str(item.get("text") or "").strip()
        for item in history
    )


def union_signals(previous: list[str], new: list[str], allowed: list[str]) -> list[str]:
    allowed_set = set(allowed)
    merged: list[str] = []
    for signal in list(previous) + list(new):
        if signal in allowed_set and signal not in merged:
            merged.append(signal)
    return merged


def goal_met(fired: list[str], allowed: list[str]) -> bool:
    return set(allowed).issubset(set(fired))
