"""Oculus visemes from text or from a library phonetic line.

These helpers mirror the browser face code. They describe a mouth shape.
They do not score a recording.
"""

from __future__ import annotations

import re

MOODS = {
    "neutral": {"smile": 0.08, "brow": 0.0},
    "happy": {"smile": 0.7, "brow": 0.16},
    "question": {"smile": 0.14, "brow": 0.9},
    "encourage": {"smile": 0.82, "brow": 0.2},
    "listen": {"smile": 0.34, "brow": 0.06},
    "examiner": {"smile": 0.12, "brow": 0.05},
}

OPEN_VOWELS = {"aa", "E", "I", "O", "U"}

_TONE_MARKS = str.maketrans(
    {
        "ā": "a",
        "á": "a",
        "ǎ": "a",
        "à": "a",
        "ē": "e",
        "é": "e",
        "ě": "e",
        "è": "e",
        "ī": "i",
        "í": "i",
        "ǐ": "i",
        "ì": "i",
        "ō": "o",
        "ó": "o",
        "ǒ": "o",
        "ò": "o",
        "ū": "u",
        "ú": "u",
        "ǔ": "u",
        "ù": "u",
        "ǖ": "v",
        "ǘ": "v",
        "ǚ": "v",
        "ǜ": "v",
        "ü": "v",
        "ń": "n",
        "ň": "n",
        "ǹ": "n",
    }
)


def _strip_tone_marks(token: str) -> str:
    return token.translate(_TONE_MARKS)


def english_visemes(text: str) -> list[str]:
    out: list[str] = []
    source = text.lower()

    def vowel(char: str) -> bool:
        return char in "aeiou"

    i = 0
    while i < len(source):
        char = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if char in " \n\t":
            i += 1
            continue
        if char in ",.;!?—-":
            out.append("sil")
            i += 1
            continue
        if char == "a":
            out.append("aa")
        elif char == "e":
            out.append("I" if nxt in "ea" else "E")
        elif char == "i" or (char == "y" and not vowel(nxt)):
            out.append("I")
        elif char == "o":
            out.append("U" if nxt in "ou" else "O")
        elif char == "u":
            out.append("U")
        elif char == "w":
            out.append("U")
        elif char == "r":
            out.append("RR")
        elif char == "y":
            out.append("I")
        elif char in "bpm":
            out.append("PP")
        elif char in "fv":
            out.append("FF")
        elif char == "t" and nxt == "h":
            out.append("TH")
            i += 1
        elif char in "cs" and nxt == "h":
            out.append("CH")
            i += 1
        elif char in "sz" or (char == "c" and nxt != "h"):
            out.append("SS")
        elif char in "td":
            out.append("DD")
        elif char in "kg":
            out.append("kk")
        elif char in "nl":
            out.append("nn")
        elif char == "j":
            out.append("CH")
        elif char == "q":
            out.append("kk")
        elif char == "x":
            out.append("SS")
        i += 1
    return out or ["sil"]


def pinyin_visemes(pinyin: str) -> list[str]:
    initials = {
        "b": "PP",
        "p": "PP",
        "m": "PP",
        "f": "FF",
        "d": "DD",
        "t": "DD",
        "n": "nn",
        "l": "nn",
        "g": "kk",
        "k": "kk",
        "h": "kk",
        "j": "CH",
        "q": "CH",
        "x": "SS",
        "r": "RR",
        "z": "SS",
        "c": "SS",
        "s": "SS",
        "y": "I",
        "w": "U",
        "zh": "CH",
        "ch": "CH",
        "sh": "CH",
    }
    out: list[str] = []
    for raw in pinyin.lower().split():
        syl = re.sub(r"[1-5]", "", _strip_tone_marks(raw))
        if not syl:
            continue
        matched = re.match(r"^(zh|ch|sh|b|p|m|f|d|t|n|l|g|k|h|j|q|x|r|z|c|s|y|w)", syl)
        head = matched.group(1) if matched else ""
        if head and head in initials:
            out.append(initials[head])
        fin = syl[len(head) :]
        if re.search(r"iang|iong|uang|ang|ao|ua|ia", fin):
            out.append("aa")
        elif re.search(r"iong|ong|ou|uo", fin):
            out.append("O")
        elif re.search(r"eng|en|ei|ie|ui|ve", fin):
            out.append("E")
        elif "i" in fin:
            out.append("I")
        elif "u" in fin or "v" in fin or "ü" in fin:
            out.append("U")
        elif "o" in fin:
            out.append("O")
        elif "e" in fin:
            out.append("E")
        elif "a" in fin:
            out.append("aa")
        else:
            out.append("aa")
    return out or ["sil"]


def viseme_at(visemes: list[str], elapsed_ms: float, step_ms: float, clip_ms: float) -> str:
    """Mouth shape during a clip. Resting ``sil`` by 200ms after the clip ends."""
    if elapsed_ms >= clip_ms:
        return "sil"
    if not visemes:
        return "sil"
    index = min(len(visemes) - 1, int(elapsed_ms // step_ms))
    return visemes[index]


def synthesis_request(partner: dict, line_lang: str, accent: str) -> dict:
    """Language tags for speechSynthesis. Cantonese never falls back to zh-CN."""
    gender = partner["gender"]
    if line_lang == "yue":
        return {"langs": ["zh-HK", "yue"], "gender": gender, "forbid": ["zh-CN", "zh-TW"]}
    if line_lang == "cmn":
        return {"langs": ["zh-CN"], "gender": gender, "forbid": []}
    if partner.get("region") == "UK":
        prefer = "en-GB"
    else:
        prefer = accent if accent in ("en-GB", "en-US") else "en-GB"
    return {"langs": [prefer], "gender": gender, "forbid": []}
