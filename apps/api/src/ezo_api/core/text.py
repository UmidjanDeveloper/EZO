"""Text helpers shared by language detection, intent and memory scoring."""

from __future__ import annotations

import re
import unicodedata

# Uzbek Latin uses several look-alike apostrophes in o‘, g‘ and tutuq belgisi.
_APOSTROPHES = str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'", "´": "'"})
_WORD_RE = re.compile(r"[\w']+", re.UNICODE)


def normalize(text: str) -> str:
    """Lowercase, NFC-normalize and unify apostrophes."""
    return unicodedata.normalize("NFC", text).translate(_APOSTROPHES).lower()


def tokenize(text: str) -> list[str]:
    return [t.strip("'") for t in _WORD_RE.findall(normalize(text)) if t.strip("'")]


_QUOTED = re.compile(
    r"«([^»]{1,200})»|“([^”]{1,200})”|„([^“”]{1,200})[“”]|\"([^\"]{1,200})\""
    r"|(?<!\w)'([^']{1,200})'(?!\w)|(?<!\w)‘([^’]{1,200})’(?!\w)"
)


def quoted(text: str) -> list[str]:
    """Texts in quotation marks, in order: «…», “…”, „…“, "…" and '…' / ‘…’ around words.
    Apostrophes inside Uzbek words (o'zbek, yo‘q) are not taken as quotes."""
    return [next(g for g in m.groups() if g is not None) for m in _QUOTED.finditer(text)]
