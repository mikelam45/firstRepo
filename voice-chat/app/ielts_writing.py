"""Original writing prompts and the deterministic checks from §19.7.

The speaking UI does not submit writing. The checks are here so a later
writing review cannot skip the length gate or an opinion in Academic Task 1.
"""

from __future__ import annotations

from app.ielts_length import writing_flags
from app.ielts_round import round_ielts_mean

PROMPTS = {
    "task2-practical-skills": {
        "task": "task2",
        "module": "both",
        "prompt": (
            "Some people think adults should spend their free time learning practical skills "
            "instead of taking academic courses. To what extent do you agree or disagree?"
        ),
        "minimum_words": 250,
    },
    "general-task1-thank-you": {
        "task": "task1",
        "module": "general",
        "prompt": (
            "You recently stayed at a friend’s home. Write a letter to thank them. "
            "Say what you enjoyed, describe one thing you did together, and invite them to stay with you."
        ),
        "tone": "informal",
        "minimum_words": 150,
    },
    "academic-task1-visitors": {
        "task": "task1",
        "module": "academic",
        "prompt": "Summarise the main features and make comparisons. No opinion.",
        "table": {
            "unit": "visitors in millions",
            "years": [2015, 2018, 2021, 2024],
            "rows": {"City A": [2.1, 2.8, 1.2, 3.6], "City B": [3.4, 3.1, 1.5, 2.9]},
        },
        "minimum_words": 150,
    },
}


def check_script(task: str, module: str, text: str) -> dict:
    flags = writing_flags(task, module, text)
    return {"flags": flags, "overall_allowed": True}


def writing_overall(bands: list[int]) -> float | None:
    if len(bands) != 4 or any(not isinstance(band, int) for band in bands):
        return None
    return round_ielts_mean(bands)
