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
