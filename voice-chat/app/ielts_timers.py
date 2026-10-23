"""Client-timer rules the server can pin. The browser clock still does the hard stop."""

from __future__ import annotations

PART2_PREP_MS = 60_000
PART2_SPEAK_MS = 120_000
MOCK_PART_MS = 300_000
PART1_WINDDOWN_MS = 255_000  # 4:15 of a 5:00 part
CONTINUE_PROMPT = "Can you tell me anything else?"


def mic_allowed(phase: str) -> bool:
    return phase != "part2_prep"


def send_allowed(phase: str) -> bool:
    return phase != "part2_prep"


def part2_on_submit(speech_ms: int | None, already_continued: bool, hard_stop: bool) -> dict:
    if hard_stop or speech_ms is None:
        return {"end": True, "prompt": None}
    if speech_ms < 60_000 and not already_continued:
        return {"end": False, "prompt": CONTINUE_PROMPT}
    return {"end": True, "prompt": None}
