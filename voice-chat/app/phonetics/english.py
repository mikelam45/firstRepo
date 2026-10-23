"""English IPA from phonemizer/espeak-ng, with a small local fallback.

The fallback is a grapheme table for when espeak is missing. It is not a
phoneme scorer and it does not claim to have heard the learner.
"""

from __future__ import annotations

_CACHE: dict[tuple[str, str], tuple[str, str]] = {}

# Word-level pins so en-GB and en-US still differ if espeak is absent.
_GB = {
    "could": "kʊd",
    "i": "aɪ",
    "get": "ɡɛt",
    "a": "ɐ",
    "coffee": "kˈɒfi",
    "please": "plˈiːz",
    "latte": "lˈɑːteɪ",
    "the": "ðə",
    "station": "stˈeɪʃən",
    "way": "weɪ",
    "to": "tuː",
    "you": "juː",
    "which": "wˈɪtʃ",
    "tell": "tˈɛl",
    "me": "miː",
}
_US = {
    **_GB,
    "coffee": "kˈɔfi",
    "a": "ə",
}


def english_ipa(text: str, accent: str) -> tuple[str, str]:
    lang = "en-gb" if accent == "en-GB" else "en-us"
    key = (lang, text.strip())
    if key in _CACHE:
        return _CACHE[key]
    ipa, engine = _phonemize(key[1], lang)
    _CACHE[key] = (ipa, engine)
    return ipa, engine


def _phonemize(text: str, lang: str) -> tuple[str, str]:
    if not text:
        return "", "empty"
    try:
        from phonemizer import phonemize

        raw = phonemize(
            text,
            language=lang,
            backend="espeak",
            with_stress=True,
            strip=True,
            preserve_punctuation=False,
            njobs=1,
        )
        ipa = " ".join(str(raw).split())
        if ipa:
            return ipa, "phonemizer"
    except Exception:
        pass
    return _fallback(text, lang), "local-fallback"


def _fallback(text: str, lang: str) -> str:
    table = _GB if lang == "en-gb" else _US
    words = []
    for raw in text.replace(",", " ").replace("?", " ").replace(".", " ").split():
        key = raw.strip("'\"").lower()
        if not key:
            continue
        words.append(table.get(key, _letters(key)))
    return " ".join(words)


def _letters(word: str) -> str:
    # Honest stand-in so a missing espeak install still returns a phonetic string.
    return word
