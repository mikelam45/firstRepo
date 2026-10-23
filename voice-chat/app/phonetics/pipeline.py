"""Segment a coach line and attach library readings. Model phonetics are discarded."""

from __future__ import annotations

import re

from app.phonetics.cantonese import cantonese_reading
from app.phonetics.english import english_ipa
from app.phonetics.putonghua import putonghua_reading
from app.phonetics.segment import segment
from app.visemes import english_visemes, pinyin_visemes


def annotate(
    text: str | None,
    target: str,
    accent: str = "en-GB",
    pinyin_tone: str = "mark",
    jyutping_overrides: dict | None = None,
    pinyin_phrases: dict | None = None,
) -> dict:
    if not text or not str(text).strip():
        return _empty(target, accent)
    parts: list[str] = []
    syllables: list[dict] = []
    visemes: list[str] = []
    complete = True
    engines: list[str] = []
    for kind, span in segment(text):
        if kind == "han":
            if target == "yue":
                reading, ok, syll = cantonese_reading(span, jyutping_overrides)
                engines.append("tojyutping")
                visemes.extend(pinyin_visemes(reading.replace("·", " ")))
            else:
                reading, ok, syll = putonghua_reading(span, pinyin_tone, pinyin_phrases)
                engines.append("pypinyin")
                visemes.extend(pinyin_visemes(_numericish(reading)))
            if not ok:
                complete = False
            if reading:
                parts.append(reading)
            syllables.extend(syll)
        elif kind == "latin":
            ipa, engine = english_ipa(span, accent)
            engines.append(engine)
            if ipa:
                parts.append(f"/{ipa}/")
                visemes.extend(_ipa_visemes(ipa))
        elif kind == "numeral":
            parts.append(span)
    phonetic = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if not visemes:
        visemes = english_visemes(text) if target == "en" else ["sil"]
    return {
        "phonetic": phonetic,
        "phonetic_complete": complete,
        "phonetic_system": _system(target, accent),
        "syllables": syllables,
        "visemes": visemes,
        "engine": engines[0] if engines else None,
    }


def _empty(target: str, accent: str) -> dict:
    return {
        "phonetic": "",
        "phonetic_complete": True,
        "phonetic_system": _system(target, accent),
        "syllables": [],
        "visemes": ["sil"],
        "engine": None,
    }


def _system(target: str, accent: str) -> str:
    if target == "yue":
        return "jyutping"
    if target == "cmn":
        return "pinyin"
    return "ipa-rp" if accent == "en-GB" else "ipa-ga"


def _numericish(reading: str) -> str:
    """Viseme mapping strips tone digits. Tone-mark pinyin still has initials."""
    return reading.replace("·", " ")


_IPA = [
    ("tʃ", "CH"),
    ("dʒ", "CH"),
    ("aɪ", "aa"),
    ("aʊ", "aa"),
    ("ɔɪ", "O"),
    ("eɪ", "E"),
    ("oʊ", "O"),
    ("əʊ", "O"),
    ("iː", "I"),
    ("uː", "U"),
    ("ɔː", "O"),
    ("ɑː", "aa"),
    ("ɜː", "E"),
    ("ɪə", "I"),
    ("eə", "E"),
    ("ʊə", "U"),
    ("ɪ", "I"),
    ("ʊ", "U"),
    ("ɒ", "O"),
    ("ɔ", "O"),
    ("ɑ", "aa"),
    ("æ", "aa"),
    ("ʌ", "aa"),
    ("ə", "E"),
    ("ɛ", "E"),
    ("θ", "TH"),
    ("ð", "TH"),
    ("ʃ", "CH"),
    ("ʒ", "CH"),
    ("ŋ", "nn"),
    ("p", "PP"),
    ("b", "PP"),
    ("m", "PP"),
    ("f", "FF"),
    ("v", "FF"),
    ("t", "DD"),
    ("d", "DD"),
    ("k", "kk"),
    ("ɡ", "kk"),
    ("g", "kk"),
    ("n", "nn"),
    ("l", "nn"),
    ("s", "SS"),
    ("z", "SS"),
    ("ɹ", "RR"),
    ("r", "RR"),
    ("j", "I"),
    ("w", "U"),
]


def _ipa_visemes(ipa: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(ipa):
        if ipa[i].isspace() or ipa[i] in "ˈˌ/:":
            i += 1
            continue
        matched = False
        for token, viseme in _IPA:
            if ipa.startswith(token, i):
                out.append(viseme)
                i += len(token)
                matched = True
                break
        if not matched:
            i += 1
    return out or ["sil"]


# Imported by tests that want the letter fallback as well.
__all__ = ["annotate", "english_visemes", "pinyin_visemes"]
