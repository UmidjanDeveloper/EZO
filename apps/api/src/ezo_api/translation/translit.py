"""Uzbek Latin ↔ Cyrillic transliteration, deterministic (no model, works offline).

Rules follow the 1995 Latin alphabet and common office practice:
- Cyrillic → Latin is rule based: е → "ye" at the start of a word and after a vowel,
  ц → "s" at the start / after a consonant and "ts" after a vowel, ъ → tutuq belgisi,
  ь is dropped.
- Latin → Cyrillic needs a little vocabulary because the Latin alphabet merged some
  letters: ц (-tsiya, -ksiya, -nsiya and a short list of common loanwords) and the
  soft sign of month names. Everything else is rule based: e → э at the start of a word
  and after a vowel, ye/yo/yu/ya → е/ё/ю/я (but y + o‘ stays й + ў), o‘/g‘ → ў/ғ and
  any other apostrophe inside a word → ъ.
URLs and e-mail addresses are never changed.

`spans()` returns the output piece for every input position, so Word files can be
converted run by run without losing formatting (see `translation.documents`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Script = Literal["latin", "cyrillic"]
Apostrophe = Literal["ascii", "modifier"]

APOSTROPHES = "'‘’ʻʼ`´"
_PROTECTED = re.compile(
    r"(?:https?://|www\.)\S+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\b[\w-]+\.(?:uz|com|org|net|ru|gov)\b"
)
_VOWELS_CYR = set("аеёиоуэюяўы")
_VOWELS_LAT = set("aeiou")

_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo", "ж": "j", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ч": "ch", "ш": "sh",
    "щ": "sh", "э": "e", "ю": "yu", "я": "ya", "қ": "q", "ҳ": "h", "ы": "i",
}  # fmt: skip
_LAT_TO_CYR = {
    "a": "а", "b": "б", "d": "д", "f": "ф", "g": "г", "h": "ҳ", "i": "и", "j": "ж",
    "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "x": "х", "y": "й", "z": "з", "c": "ц",
    "w": "в",
}  # fmt: skip
_Y_PAIRS = {"e": "е", "o": "ё", "u": "ю", "a": "я"}

# Latin → Cyrillic vocabulary: stem → (Cyrillic stem, form when the word is exactly the stem).
_LAT_STEMS: dict[str, tuple[str, str]] = {
    "yanvar": ("январ", "январь"),
    "fevral": ("феврал", "февраль"),
    "aprel": ("апрел", "апрель"),
    "iyun": ("июн", "июнь"),
    "iyul": ("июл", "июль"),
    "sentabr": ("сентябр", "сентябрь"),
    "oktabr": ("октябр", "октябрь"),
    "noyabr": ("ноябр", "ноябрь"),
    "dekabr": ("декабр", "декабрь"),
    "sentr": ("центр", "центр"),
    "sement": ("цемент", "цемент"),
    "sirk": ("цирк", "цирк"),
    "sitat": ("цитат", "цитат"),
    "sivilizats": ("цивилизац", "цивилизац"),
    "sotsial": ("социал", "социал"),
    "sotsiolog": ("социолог", "социолог"),
    "litsey": ("лицей", "лицей"),
    "litsenz": ("лицензи", "лицензи"),
    "prinsip": ("принцип", "принцип"),
    "konsert": ("концерт", "концерт"),
    "konsep": ("концеп", "концеп"),
    "obyekt": ("объект", "объект"),
    "subyekt": ("субъект", "субъект"),
}
_LAT_INSIDE = (("tsiya", "ция"), ("ksiya", "кция"), ("nsiya", "нция"))
_CYR_STEMS = {"сентябр": "sentabr", "октябр": "oktabr"}


@dataclass(frozen=True, slots=True)
class Span:
    """`out` replaces `text[start:end]`."""

    start: int
    end: int
    out: str


def detect_script(text: str) -> Script | None:
    latin = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    cyrillic = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch.lower() in "ёўқғҳ")
    if latin == cyrillic == 0:
        return None
    return "cyrillic" if cyrillic > latin else "latin"


def _is_apostrophe(ch: str) -> bool:
    return ch in APOSTROPHES


def _words(text: str) -> list[tuple[int, int, bool]]:
    """(start, end, is_word) pieces. Apostrophes belong to a word inside it, and at its
    end after o/g (tog‘)."""
    protected = [(m.start(), m.end()) for m in _PROTECTED.finditer(text)]
    pieces: list[tuple[int, int, bool]] = []
    i = 0
    n = len(text)
    while i < n:
        hit = next((p for p in protected if p[0] == i), None)
        if hit is not None:
            pieces.append((hit[0], hit[1], False))
            i = hit[1]
            continue
        if text[i].isalpha():
            j = i + 1
            while j < n:
                ch = text[j]
                inside = _is_apostrophe(ch) and (
                    (j + 1 < n and text[j + 1].isalpha()) or text[j - 1].lower() in "og"
                )
                if ch.isalpha() or inside:
                    j += 1
                else:
                    break
            pieces.append((i, j, True))
            i = j
        else:
            j = i + 1
            while j < n and not text[j].isalpha() and not any(p[0] == j for p in protected):
                j += 1
            pieces.append((i, j, False))
            i = j
    return pieces


def _case(out: str, source: str, whole_word_upper: bool) -> str:
    if not source[:1].isupper():
        return out
    if whole_word_upper:
        return out.upper()
    return out[:1].upper() + out[1:]


def _word_to_latin(word: str, offset: int, apostrophe: Apostrophe) -> list[Span]:
    tutuq = "ʼ" if apostrophe == "modifier" else "'"
    modifier = "ʻ" if apostrophe == "modifier" else "'"
    lower = word.lower()
    upper = len(word) > 1 and word.isupper()
    spans: list[Span] = []
    i = 0
    for stem, latin in _CYR_STEMS.items():
        if lower.startswith(stem):
            spans.append(Span(offset, offset + len(stem), _case(latin, word, upper)))
            i = len(stem)
            if lower[i : i + 1] == "ь":
                spans.append(Span(offset + i, offset + i + 1, ""))
                i += 1
            break
    while i < len(word):
        ch, low = word[i], lower[i]
        prev = lower[i - 1] if i else ""
        nxt = lower[i + 1] if i + 1 < len(word) else ""
        if low == "е":
            out = "ye" if (not prev or prev in _VOWELS_CYR or prev in "ъь") else "e"
        elif low == "ц":
            out = "ts" if prev and prev in _VOWELS_CYR else "s"
        elif low == "ў":
            out = "o" + modifier
        elif low == "ғ":
            out = "g" + modifier
        elif low == "ъ":
            out = "" if nxt in ("е", "ё", "ю", "я") or prev == "ў" else tutuq
        elif low == "с" and nxt == "ҳ":
            out = "s" + tutuq  # сҳ → s'h, so it is not read as sh
        elif low == "ь":
            out = "y" if nxt == "о" else ""
        else:
            out = _CYR_TO_LAT.get(low, ch)
        if ch.isupper() and out:
            out = out.upper() if upper else out[:1].upper() + out[1:]
        spans.append(Span(offset + i, offset + i + 1, out))
        i += 1
    return spans


def _word_to_cyrillic(word: str, offset: int) -> list[Span]:
    lower = word.lower()
    for mark in APOSTROPHES:
        lower = lower.replace(mark, "'")
    upper = len(word) > 1 and all(c.isupper() for c in word if c.isalpha())
    spans: list[Span] = []
    i = 0
    for stem, (cyr, exact) in _LAT_STEMS.items():
        if lower.startswith(stem):
            out = exact if lower == stem else cyr
            spans.append(Span(offset, offset + len(stem), _case(out, word, upper)))
            i = len(stem)
            break
    while i < len(word):
        low = lower[i]
        prev = lower[i - 1] if i else ""
        rest = lower[i:]
        inside = next(((lat, cyr) for lat, cyr in _LAT_INSIDE if rest.startswith(lat)), None)
        if inside is not None:
            lat, cyr = inside
            spans.append(Span(offset + i, offset + i + len(lat), _case(cyr, word[i:], upper)))
            i += len(lat)
            continue
        two = rest[:2]
        three = rest[:3]
        if two in ("o'", "g'"):
            out, size = ("ў" if low == "o" else "ғ"), 2
        elif two in ("sh", "ch"):
            out, size = ("ш" if two == "sh" else "ч"), 2
        elif low == "y" and len(rest) > 1 and rest[1] in _Y_PAIRS and three != "yo'":
            out, size = _Y_PAIRS[rest[1]], 2
        elif low == "e":
            out, size = ("э" if not prev or prev == "'" or prev in _VOWELS_LAT else "е"), 1
        elif low == "'":
            # Is'hoq: the apostrophe only separates s and h.
            out, size = ("" if prev in "sc" and rest[1:2] == "h" else "ъ"), 1
        elif low in _LAT_TO_CYR:
            out, size = _LAT_TO_CYR[low], 1
        else:
            spans.append(Span(offset + i, offset + i + 1, word[i]))
            i += 1
            continue
        if word[i].isupper():
            out = out.upper()
        spans.append(Span(offset + i, offset + i + size, out))
        i += size
    return spans


def spans(text: str, to: Script, *, apostrophe: Apostrophe = "ascii") -> list[Span]:
    """Every input position covered once, in order."""
    result: list[Span] = []
    for start, end, is_word in _words(text):
        piece = text[start:end]
        if not is_word:
            result.append(Span(start, end, piece))
        elif to == "latin" and any("а" <= c.lower() <= "я" or c.lower() in "ёўқғҳ" for c in piece):
            result += _word_to_latin(piece, start, apostrophe)
        elif to == "cyrillic" and any("a" <= c.lower() <= "z" for c in piece):
            result += _word_to_cyrillic(piece, start)
        else:
            result.append(Span(start, end, piece))
    return result


def transliterate(text: str, to: Script, *, apostrophe: Apostrophe = "ascii") -> str:
    return "".join(s.out for s in spans(text, to, apostrophe=apostrophe))


def to_cyrillic(text: str) -> str:
    return transliterate(text, "cyrillic")


def to_latin(text: str, *, apostrophe: Apostrophe = "ascii") -> str:
    return transliterate(text, "latin", apostrophe=apostrophe)
