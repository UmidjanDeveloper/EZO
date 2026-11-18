"""Which language the learner wants to practise or be examined in, from their own words.

"Rus tilidan imtihon ol", "nemis tilida gaplashamiz", "test my French", "проверь мой
испанский" → ru / de / fr / es. English stays the default practice language.
"""

from __future__ import annotations

import re

from ezo_api.core.text import normalize

# code → (English name, the language's own name)
PRACTICE_LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "English"),
    "ru": ("Russian", "русский"),
    "de": ("German", "Deutsch"),
    "fr": ("French", "français"),
    "es": ("Spanish", "español"),
    "it": ("Italian", "italiano"),
    "tr": ("Turkish", "Türkçe"),
    "ar": ("Arabic", "العربية"),
    "ko": ("Korean", "한국어"),
    "zh": ("Chinese (Mandarin)", "中文"),
    "ja": ("Japanese", "日本語"),
    "uz": ("Uzbek (Latin script)", "o'zbekcha"),
    "kk": ("Kazakh", "қазақша"),
    "pt": ("Portuguese", "português"),
}

# Stems in Uzbek (Latin and Cyrillic), English and Russian. Matched at a word start.
_NAMES: tuple[tuple[str, str], ...] = (
    ("en", r"ingliz|english|англи|инглиз"),
    ("ru", r"rus(?:cha|ch|sian|\s+tili)|rus tili|russian|русск|по-русски|рус тил"),
    ("de", r"nemis|german|deutsch|немец|немис"),
    ("fr", r"fransuz|french|français|francais|француз"),
    ("es", r"ispan|spanish|español|espanol|испан"),
    ("it", r"italyan|italian|итальян"),
    ("tr", r"turk(?:cha|ish| tili)|turk tili|türk|турец|турк тил"),
    ("ar", r"arab|араб"),
    ("ko", r"koreys|korean|корей"),
    ("zh", r"xitoy|chinese|mandarin|китай|хитой"),
    ("ja", r"yapon|japanese|япон"),
    ("uz", r"o'zbek|uzbek|узбек|ўзбек"),
    ("kk", r"qozoq|kazakh|казах"),
    ("pt", r"portugal|portuguese|португал"),
)
_COMPILED = [(code, re.compile(rf"(?<!\w)(?:{stems})")) for code, stems in _NAMES]

# A language name plus a practice or exam word, in either order.
_ACTIVITY = (
    r"(imtihon|ekzamen|examiner|exam\b|test|sinab|sina|daraja|level|mashq|gaplash|suhbat|"
    r"practice|practise|speak|speaking|o'rgat|dars|экзамен|экзаменатор|тест|уровен|практик|"
    r"поговор|разговор|урок|имтиҳон|машқ|гаплаш)"
)


def detect_practice_language(text: str) -> str | None:
    """The first language named in the text, or None."""
    norm = normalize(text)
    best: tuple[int, str] | None = None
    for code, pattern in _COMPILED:
        found = pattern.search(norm)
        if found and (best is None or found.start() < best[0]):
            best = (found.start(), code)
    return best[1] if best else None


def language_name(code: str) -> str:
    return PRACTICE_LANGUAGES.get(code, PRACTICE_LANGUAGES["en"])[0]


ALL_STEMS = "|".join(stems for _, stems in _NAMES)
LANGUAGE_ACTIVITY = (
    rf"(?<!\w)(?:{ALL_STEMS})\w*(?:\s+\S+){{0,4}}?\s+{_ACTIVITY}|"
    rf"{_ACTIVITY}\w*(?:\s+\S+){{0,4}}?\s+(?:{ALL_STEMS})"
)
"""For the intent classifier: "rus tilidan imtihon ol", "speak German with me"."""
