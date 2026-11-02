"""Cantonese LSHK Jyutping via ToJyutping.

``customize`` returns a new converter. The default converter is never mutated,
so a scenario override cannot leak into another scenario.
"""

from __future__ import annotations

import ToJyutping

from app.phonetics.segment import is_han

_CACHE: dict[tuple[tuple[str, str], ...], object] = {}


def converter_for(overrides: dict | None):
    if not overrides:
        return ToJyutping
    key = tuple(sorted((str(k), str(v)) for k, v in overrides.items()))
    if key not in _CACHE:
        _CACHE[key] = ToJyutping.customize(dict(overrides))
    return _CACHE[key]


def cantonese_reading(
    text: str,
    overrides: dict | None = None,
) -> tuple[str, bool, list[dict]]:
    converter = converter_for(overrides)
    pairs = converter.get_jyutping_list(text)
    candidate_map = {char: options for char, options in converter.get_jyutping_candidates(text)}
    tokens: list[str] = []
    syllables: list[dict] = []
    complete = True
    for char, reading in pairs:
        if not is_han(char):
            continue
        options = candidate_map.get(char) or []
        ambiguous = _ambiguous(options)
        if not reading:
            tokens.append("·")
            complete = False
            syllables.append(
                {"text": char, "reading": "·", "ambiguous": False, "candidates": options[:4]}
            )
            continue
        tokens.append(reading)
        syllables.append(
            {
                "text": char,
                "reading": reading,
                "ambiguous": ambiguous,
                "candidates": options[:4],
            }
        )
    return " ".join(tokens), complete, syllables


def _ambiguous(options: list[str]) -> bool:
    if len(options) < 2:
        return False
    return _tone(options[0]) != _tone(options[1])


def _tone(reading: str) -> str:
    return reading[-1] if reading and reading[-1].isdigit() else ""
