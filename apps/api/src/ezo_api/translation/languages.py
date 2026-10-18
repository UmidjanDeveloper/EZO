# ruff: noqa: E501  (rule text is kept on readable lines)
"""Languages EZO translates between, and reading them from a request.

Codes: "uz" (Uzbek, Latin script), "uz-cyrl" (Uzbek, Cyrillic script), "ru", "en".
Uzbek in Cyrillic is produced by translating into Uzbek and converting the script
deterministically (`translit`), so both scripts read the same.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ezo_api.core.language import detect_language
from ezo_api.core.text import normalize
from ezo_api.translation.translit import detect_script

Code = Literal["uz", "uz-cyrl", "ru", "en"]
Domain = Literal["general", "official", "academic", "business", "technical", "legal"]

NAMES: dict[str, str] = {
    "uz": "Uzbek (Latin script)",
    "uz-cyrl": "Uzbek (Cyrillic script)",
    "ru": "Russian",
    "en": "English",
}
LABELS: dict[str, str] = {"uz": "O'zbekcha", "uz-cyrl": "Ўзбекча", "ru": "Русский", "en": "English"}

_MENTION = re.compile(
    r"(?P<cyrl>(?:o'zbek\w*\s+)?(?:kirill\w*|кирилл\w*|cyrillic\w*))"
    r"|(?P<uz>(?:o'zbek\w*|uzbek\w*|узбек\w*)(?:\s+(?:lotin\w*|latin\w*))?|lotin\w*|latin\w*)"
    r"|(?P<ru>\brus(?:cha|\s+til)\w*|\brus\b|russian\w*|русск\w*|\bрус\w*)"
    r"|(?P<en>ingliz\w*|english\w*|англ\w*)"
)
_SOURCE_AFTER = re.compile(r"(dan|dagi|da)$")
_SOURCE_BEFORE = re.compile(r"\b(from|с|из|со)\s*$")
_TARGET_AFTER = re.compile(r"(ga|ka|qa)$")
_TARGET_BEFORE = re.compile(r"\b(to|into|in|на|в)\s*$")

_DOMAINS: tuple[tuple[Domain, re.Pattern[str]], ...] = (
    ("legal", re.compile(r"\b(huquqiy|yuridik|legal|юридическ|правов)")),
    ("official", re.compile(r"\b(rasmiy|official|официальн|деловое письмо)")),
    ("academic", re.compile(r"\b(ilmiy|akademik|academic|scientific|научн|академическ)")),
    ("technical", re.compile(r"\b(texnik|technical|техническ)")),
    ("business", re.compile(r"\b(biznes|business|commercial|делов|коммерческ)")),
)
DOMAIN_RULES: dict[str, str] = {
    "general": "Natural, idiomatic language for the target reader.",
    "official": "Official correspondence: the target language's standard administrative terms and forms of address; neutral and precise.",
    "academic": "Academic text: precise terminology, cautious claims kept as cautious, citations and references unchanged.",
    "business": "Business text: clear and professional; product, company and brand names unchanged.",
    "technical": "Technical text: exact terms, units, parameters and code unchanged.",
    "legal": "Legal text: faithful rather than free; keep the structure of articles and clauses; keep article numbers, document numbers and dates exactly; do not explain or interpret.",
}


@dataclass(frozen=True, slots=True)
class LanguageRequest:
    source: str | None
    target: str | None


def base(code: str) -> str:
    """Language without the script: "uz-cyrl" → "uz"."""
    return "uz" if code.startswith("uz") else code


def parse_languages(text: str) -> LanguageRequest:
    """Source and target languages named in a request.

    "ruschadan o'zbek lotiniga" → ru → uz; "inglizchaga" → en; "с русского на узбекский"
    → ru → uz; "kirillga" → uz-cyrl. A name marked as the source (-dan, from, с) is the
    source; the target is the one marked as a target (-ga, to, на), else the last one."""
    norm = normalize(text)
    mentions: list[tuple[str, bool, bool]] = []
    for match in _MENTION.finditer(norm):
        code = {"cyrl": "uz-cyrl", "uz": "uz", "ru": "ru", "en": "en"}[match.lastgroup or "uz"]
        word = match.group(0).split()[-1]
        before = norm[max(0, match.start() - 8) : match.start()]
        is_source = bool(_SOURCE_AFTER.search(word) or _SOURCE_BEFORE.search(before))
        is_target = bool(_TARGET_AFTER.search(word) or _TARGET_BEFORE.search(before))
        mentions.append((code, is_source and not is_target, is_target))
    source = next((code for code, src, _ in mentions if src), None)
    targets = [code for code, src, _ in mentions if not src]
    marked = [code for code, src, tgt in mentions if tgt and not src]
    target = marked[0] if marked else (targets[-1] if targets else None)
    if source is not None and base(source) == base(target or "") and source != target:
        source = None  # "lotindan kirillga" is a script change, not a source language
    return LanguageRequest(source=source, target=target)


def detect(text: str) -> str:
    """Language of a text, with the Uzbek script."""
    language = detect_language(text[:4000])
    if language == "uz" and detect_script(text[:4000]) == "cyrillic":
        return "uz-cyrl"
    return language


def domain_of(text: str) -> Domain:
    norm = normalize(text)
    return next((name for name, pattern in _DOMAINS if pattern.search(norm)), "general")


def default_target(source: str, user_language: str) -> str:
    """The target when none is named: the user's language, or English for Uzbek text."""
    if base(source) != base(user_language):
        return user_language
    return "en" if base(source) == "uz" else "uz"
