"""Recognising academic requests: research plans with literature, and reference lists to
format in a citation style."""

from __future__ import annotations

import re

from ezo_api.academic.citations import Style, style_from
from ezo_api.core.text import normalize
from ezo_api.translation.translit import to_latin

_RESEARCH = re.compile(
    r"\b(ilmiy (manba|adabiyot|maqola)\w*|adabiyot\w* (top|izla|qidir|sharh|tahlil|ro'yxat)\w*|"
    r"manbalar\w* top\w*|tadqiqot reja\w*|tadqiqot dastur\w*|dissertatsiya\w* (reja|mavzu)\w*|"
    r"magistrlik (ishi|dissertatsiya)\w*|bitiruv (malakaviy )?ish\w*|kurs ishi\w* reja\w*|"
    r"literature (review|search)|research (plan|outline|proposal)|thesis (plan|outline)|"
    r"find (scientific |academic |research )?(sources|papers|articles|literature)|"
    r"обзор литератур\w*|план исследовани\w*|научн\w* (источник|стать|литератур)\w*|"
    r"найди (источник|стать)\w*|план диссертаци\w*)"
)
_REFERENCES = re.compile(
    r"\b(adabiyot\w*|manba\w*|references?|bibliograph\w*|citations?|"
    r"список\w* литератур\w*|литератур\w*|источник\w*|библиограф\w*)"
)
_FORMAT_VERB = re.compile(
    r"\b(formatla|formatiga|formatida|uslubida|o'tkaz|aylantir|tuz|qilib|convert|format|"
    r"style|cite|оформи|оформл|переведи|по (гост|apa))"
)


def _norm(text: str) -> str:
    return normalize(text) + " " + normalize(to_latin(text))


def wants_research_plan(text: str) -> bool:
    return bool(_RESEARCH.search(_norm(text)))


def citation_request(text: str) -> Style | None:
    """ "Shu adabiyotlarni APA formatiga o'tkaz" → apa."""
    norm = _norm(text)
    style = style_from(norm)
    if style and _REFERENCES.search(norm) and _FORMAT_VERB.search(norm):
        return style
    return None
