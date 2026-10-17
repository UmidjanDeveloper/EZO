"""Lightweight language detection for Uzbek, English and Russian.

Heuristic and dependency-free. Designed to be replaced by a model-based
detector later; callers only depend on `detect_language`.
"""

from __future__ import annotations

from typing import Literal

from ezo_api.core.text import normalize, tokenize

Language = Literal["uz", "en", "ru"]
SUPPORTED_LANGUAGES: tuple[Language, ...] = ("uz", "en", "ru")
DEFAULT_LANGUAGE: Language = "uz"

# Letters that only appear in Uzbek Cyrillic.
_UZ_CYRILLIC = set("ўқғҳ")

_UZ_WORDS = set(
    """
    men sen siz biz u bu va uchun bilan emas yo'q ha qanday nima nega qachon qayerda kerak
    mumkin bor edi qilamiz qil qiling ber bering tayyorla yordam salom rahmat yaxshi juda
    menga sizga mening sening bizning ham lekin agar endi bugun ertaga kecha qilib haqida
    tushuntir top oxirgi qaror qarorini nechta qaysi kim boshla davom qani yoz yasab o'zbek
    tilida qanaqa qalaysan qalesan assalomu alaykum xayr iltimos ko'p kam bo'ladi bo'lsa
    qiladi nimaga shu o'sha yana faqat hammasi loyiha loyiham eslab qol
    """.split()
)
_UZ_SUFFIXES = tuple(
    "lar larni ning dagi ni ga da dan imiz ingiz yapman yapti moqda sizmi mi chi man san "
    "miz".split()
)
_EN_WORDS = set(
    """
    the a an is are was were i you we they it and or but to of in on for with what how why
    when where please can could would should do does my your this that hello hi thanks
    let's let me help about make write explain find speaking practice want need have be
    """.split()
)


def detect_language(text: str, fallback: Language = DEFAULT_LANGUAGE) -> Language:
    """Return the most likely language of `text` (uz, en or ru)."""
    lowered = normalize(text)
    letters = [ch for ch in lowered if ch.isalpha()]
    if not letters:
        return fallback

    cyrillic = sum(1 for ch in letters if "а" <= ch <= "я" or ch in "ёўқғҳ")
    if cyrillic / len(letters) > 0.5:
        return "uz" if any(ch in _UZ_CYRILLIC for ch in lowered) else "ru"

    tokens = tokenize(text)
    if not tokens:
        return fallback
    uz_score = 0.0
    en_score = 0.0
    for token in tokens:
        if token in _UZ_WORDS or "o'" in token or "g'" in token:
            uz_score += 1.0
        elif len(token) > 4 and token.endswith(_UZ_SUFFIXES):
            uz_score += 0.5
        if token in _EN_WORDS:
            en_score += 1.0

    if uz_score == 0 and en_score == 0:
        return fallback
    return "uz" if uz_score >= en_score else "en"
