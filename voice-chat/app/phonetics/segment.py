"""Split a line into han, latin, numeral, and other spans."""

from __future__ import annotations


def is_han(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0x2CEB0 <= code <= 0x2EBEF
        or 0x30000 <= code <= 0x3134F
        or 0x31350 <= code <= 0x323AF
    )


def segment(text: str) -> list[tuple[str, str]]:
    spans: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if is_han(ch):
            j = i + 1
            while j < n and is_han(text[j]):
                j += 1
            spans.append(("han", text[i:j]))
        elif ch.isascii() and ch.isalpha():
            j = i + 1
            while j < n:
                if text[j].isascii() and (text[j].isalpha() or text[j] in "'’"):
                    j += 1
                    continue
                if text[j] in " \t,.;:!?-—":
                    k = j
                    while k < n and text[k] in " \t,.;:!?-—":
                        k += 1
                    if k < n and text[k].isascii() and text[k].isalpha():
                        j = k
                        continue
                    # Keep trailing punctuation on the English span so espeak sees the clause.
                    j = k
                    break
                break
            spans.append(("latin", text[i:j].strip()))
        elif ch.isdigit():
            j = i + 1
            while j < n and text[j].isdigit():
                j += 1
            spans.append(("numeral", text[i:j]))
        else:
            j = i + 1
            while j < n and not _starts_kept(text[j]):
                j += 1
            spans.append(("other", text[i:j]))
        i = j
    return spans


def _starts_kept(ch: str) -> bool:
    return is_han(ch) or ch.isdigit() or (ch.isascii() and ch.isalpha())
