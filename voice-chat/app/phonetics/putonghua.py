"""Putonghua readings from pypinyin.

Scenario surnames are applied with ``load_phrases_dict`` only for that call.
pypinyin stores phrases on a process-global dict, so the update is locked and
restored before the function returns. Another scenario never sees it.
儿化 is joined only for the words the product actually uses (这儿, 一点儿, …).
"""

from __future__ import annotations

import threading

from pypinyin import Style, load_phrases_dict, pinyin
from pypinyin.constants import PHRASES_DICT
from pypinyin.seg import mmseg

from app.phonetics.segment import is_han

_LOCK = threading.Lock()
_MISSING = object()

# Mark form, then numeric form. Generated as product rules on top of pypinyin,
# not as a hand-spaced rewrite of an unrelated string.
ERHUA = {
    "一点儿": ("yìdiǎnr", "yi4dian3r"),
    "一会儿": ("yíhuìr", "yi2hui4r"),
    "这儿": ("zhèr", "zhe4r"),
    "那儿": ("nàr", "na4r"),
    "哪儿": ("nǎr", "na3r"),
    "好玩儿": ("hǎowánr", "hao3wan2r"),
}


def putonghua_reading(
    text: str,
    tone: str = "mark",
    phrases: dict | None = None,
) -> tuple[str, bool, list[dict]]:
    import zhconv

    hans = zhconv.convert(text, "zh-hans")
    style = Style.TONE3 if tone == "number" else Style.TONE
    chunks = _split(hans, phrases or {})
    tokens: list[str] = []
    syllables: list[dict] = []
    complete = True
    for surface, kind in chunks:
        if kind == "erhua":
            token = ERHUA[surface][1 if tone == "number" else 0]
            tokens.append(token)
            syllables.append(
                {"text": surface, "reading": token, "ambiguous": False, "candidates": []}
            )
            continue
        if kind == "phrase":
            rows, ok = _convert(surface, style, phrases)
            if not ok:
                complete = False
            for token in rows:
                tokens.append(token)
                syllables.append(
                    {"text": surface, "reading": token, "ambiguous": False, "candidates": []}
                )
            continue
        rows, ok = _convert(surface, style, None)
        if not ok:
            complete = False
        han_chars = [ch for ch in surface if is_han(ch)]
        for ch, token in zip(han_chars, rows):
            tokens.append(token)
            if token == "·":
                complete = False
            syllables.append(
                {"text": ch, "reading": token, "ambiguous": False, "candidates": []}
            )
    return " ".join(tokens), complete, syllables


def _split(text: str, phrases: dict) -> list[tuple[str, str]]:
    keys = [(word, "erhua") for word in ERHUA] + [(word, "phrase") for word in phrases]
    keys.sort(key=lambda item: len(item[0]), reverse=True)
    parts: list[tuple[str, str]] = []
    i = 0
    while i < len(text):
        hit = None
        for word, kind in keys:
            if text.startswith(word, i):
                hit = (word, kind)
                break
        if hit:
            parts.append(hit)
            i += len(hit[0])
            continue
        j = i + 1
        while j < len(text) and not any(text.startswith(word, j) for word, _ in keys):
            j += 1
        parts.append((text[i:j], "plain"))
        i = j
    return parts


def _convert(text: str, style: Style, phrases: dict | None) -> tuple[list[str], bool]:
    rows = _pinyin(text, style, phrases)
    han_chars = [ch for ch in text if is_han(ch)]
    if len(rows) != len(text):
        rows = []
        for ch in text:
            rows.extend(_pinyin(ch, style, None))
    tokens: list[str] = []
    complete = True
    han_rows = []
    for ch, row in zip(text, rows):
        if is_han(ch):
            han_rows.append((ch, row))
    if len(han_rows) != len(han_chars):
        han_rows = [(ch, _pinyin(ch, style, None)[0]) for ch in han_chars]
    for ch, row in han_rows:
        token = row[0] if row else ""
        if not token or token == ch:
            tokens.append("·")
            complete = False
            continue
        if style == Style.TONE3:
            token = token.replace("v", "ü")
        tokens.append(token)
    return tokens, complete


def _pinyin(text: str, style: Style, phrases: dict | None) -> list[list[str]]:
    if not phrases:
        return pinyin(text, style=style, errors="default")
    saved: dict = {}
    with _LOCK:
        for key in phrases:
            saved[key] = PHRASES_DICT[key] if key in PHRASES_DICT else _MISSING
        try:
            load_phrases_dict(phrases)
            return pinyin(text, style=style, errors="default")
        finally:
            for key, value in saved.items():
                if value is _MISSING:
                    PHRASES_DICT.pop(key, None)
                else:
                    PHRASES_DICT[key] = value
            mmseg.retrain(mmseg.seg)
