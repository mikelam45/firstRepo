"""Library phonetics. English uses a local IPA table when espeak-ng is absent."""

from __future__ import annotations

import re

from pypinyin import Style, pinyin
from ToJyutping import get_jyutping_text

_TOKEN = re.compile(r"[\u3400-\u9fff]+|[A-Za-z][A-Za-z']*|\d+")

_EN_GB = {
    "could": "kʊd",
    "i": "aɪ",
    "get": "ɡet",
    "a": "ə",
    "coffee": "ˈkɒfi",
    "please": "pliːz",
    "hi": "haɪ",
    "where": "weə",
    "are": "ɑː",
    "you": "juː",
    "trying": "ˈtraɪɪŋ",
    "to": "tə",
    "do": "duː",
    "usually": "ˈjuːʒəli",
    "cook": "kʊk",
    "or": "ɔː",
    "does": "dʌz",
    "someone": "ˈsʌmwʌn",
    "else": "els",
    "in": "ɪn",
    "your": "jɔː",
    "home": "həʊm",
    "at": "æt",
    "the": "ðə",
    "station": "ˈsteɪʃn",
    "want": "wɒnt",
    "excuse": "ɪkˈskjuːz",
    "me": "miː",
    "way": "weɪ",
    "left": "left",
    "right": "raɪt",
    "roundel": "ˈraʊndl",
    "latte": "ˈlɑːteɪ",
}
_EN_US = {
    **_EN_GB,
    "coffee": "ˈkɔːfi",
    "want": "wɑːnt",
    "home": "hoʊm",
    "usually": "ˈjuːʒəli",
}


def _english_word(word: str, accent: str) -> str:
    table = _EN_US if accent == "en-US" else _EN_GB
    key = word.lower().strip("'")
    if key in table:
        return table[key]
    pieces = []
    for ch in key:
        pieces.append(
            {
                "a": "æ",
                "e": "e",
                "i": "ɪ",
                "o": "ɒ" if accent != "en-US" else "ɑ",
                "u": "ʌ",
                "y": "j",
            }.get(ch, ch)
        )
    return "".join(pieces)


def english_ipa(text: str, accent: str = "en-GB") -> str:
    words = re.findall(r"[A-Za-z][A-Za-z']*", text)
    if not words:
        return ""
    return "/" + " ".join(_english_word(word, accent) for word in words) + "/"


def _jyutping_span(text: str) -> str:
    raw = get_jyutping_text(text) or ""
    raw = raw.replace("[…]", " ").replace("[...]", " ")
    raw = re.sub(r"[^a-z0-9\s]", " ", raw.lower())
    return re.sub(r"\s+", " ", raw).strip()


def _pinyin_span(text: str, tone: str) -> str:
    style = Style.TONE3 if tone == "number" else Style.TONE
    syllables = []
    for item in pinyin(text, style=style, errors=lambda chars: []):
        if not item:
            continue
        reading = item[0]
        if not re.search(r"[A-Za-zÀ-ÿāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]", reading):
            continue
        syllables.append(reading)
    merged = []
    for reading in syllables:
        if reading in {"ér", "er", "er2"} and merged:
            merged[-1] = merged[-1] + "r"
            continue
        merged.append(reading)
    return " ".join(merged)


def transcribe(text: str, target: str, accent: str = "en-GB", pinyin_tone: str = "mark") -> dict:
    parts = []
    complete = True
    for match in _TOKEN.finditer(text or ""):
        span = match.group(0)
        if span.isdigit():
            parts.append(span)
            continue
        if re.match(r"[A-Za-z]", span):
            ipa = english_ipa(span, accent)
            parts.append(ipa.strip("/"))
            continue
        if target == "yue":
            reading = _jyutping_span(span)
        elif target == "cmn":
            reading = _pinyin_span(span, pinyin_tone)
        else:
            reading = english_ipa(span, accent).strip("/")
        if not reading or "·" in reading:
            complete = False
            reading = reading or "·"
        parts.append(reading)
    phonetic = " ".join(part for part in parts if part).strip()
    if target == "en" and phonetic and not phonetic.startswith("/"):
        phonetic = f"/{phonetic}/"
    return {"phonetic": phonetic, "phonetic_complete": complete and bool(phonetic)}
