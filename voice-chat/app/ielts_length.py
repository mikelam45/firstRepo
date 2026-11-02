"""Word counts and length gates. These are facts, not bands."""

from __future__ import annotations

import re

FUNCTION_WORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "already",
    "another",
    "around",
    "because",
    "before",
    "being",
    "below",
    "between",
    "could",
    "during",
    "inside",
    "people",
    "really",
    "should",
    "something",
    "their",
    "there",
    "these",
    "those",
    "through",
    "usually",
    "without",
    "within",
    "would",
}


def count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?", text or ""))


def content_words(text: str) -> list[str]:
    found = []
    for token in re.findall(r"[A-Za-z]+", text or ""):
        if len(token) >= 6 and token.lower() not in FUNCTION_WORDS:
            found.append(token.lower())
    return found


def speaking_gate(part: int, text: str) -> str | None:
    words = count_words(text)
    if part == 1 and words < 8:
        return "too_short"
    if part == 1 and words > 120:
        return "too_long"
    if part == 2 and words < 40:
        return "too_short"
    if part == 3 and words < 15:
        return "too_short"
    return None


def writing_flags(task: str, module: str, text: str) -> list[str]:
    words = count_words(text)
    flags: list[str] = []
    if task == "task2" and words < 250:
        flags.append("under_length")
    if task == "task1" and words < 150:
        flags.append("under_length")
    if (
        task == "task1"
        and module == "academic"
        and re.search(r"\bi think\b|\bin my opinion\b", text or "", re.I)
    ):
        flags.append("opinion_in_task_1")
    return flags
