"""Recognising translation requests (used by EzoCore to pick the agent, and by the
translation actions)."""

from __future__ import annotations

import re

from ezo_api.core.text import normalize, quoted
from ezo_api.translation import glossary
from ezo_api.translation.languages import parse_languages

TRANSLATE = re.compile(r"\b(tarjima|translat\w*|перевод\w*|перевед\w*|переведи)")
SCRIPT_WORD = re.compile(r"\b(kirill\w*|lotin\w*|cyrillic|latin\w*|кирилл\w*|латин\w*)")
SCRIPT_VERB = re.compile(
    r"\b(o'gir|o'tkaz|aylantir|yoz|convert|transliter\w*|qilib|qil\b|перевед\w*|переключ\w*|конверт\w*|сделай)"
)
BILINGUAL = re.compile(
    r"\b(ikki til\w*|bilingual|parallel\w*|side[- ]by[- ]side|двуязычн\w*|параллельн\w*)"
)
_COMMAND_HEAD = re.compile(r"^(?P<head>[^:\n]{0,200}?)\s*[:\n]\s*(?P<body>\S[\s\S]*)$")


def wants_translation(text: str) -> bool:
    """A translation, script conversion or glossary request (used to pick the agent)."""
    norm = normalize(text)
    return bool(
        glossary.add_request(text)
        or (SCRIPT_WORD.search(norm) and SCRIPT_VERB.search(norm))
        or (TRANSLATE.search(norm) and (parse_languages(text).target or inline_text(text)))
    )


def inline_text(text: str) -> str | None:
    """The text to work on when it is in the message itself: after the command and a
    colon or line break ("Inglizchaga tarjima qil: …"), or in quotation marks."""
    match = _COMMAND_HEAD.match(text.strip())
    if match:
        head = normalize(match.group("head"))
        if TRANSLATE.search(head) or SCRIPT_WORD.search(head) or SCRIPT_VERB.search(head):
            body = match.group("body").strip()
            if re.search(r"[^\W\d_]", body):
                return body
    quotes = [q for q in quoted(text) if re.search(r"[^\W\d_]{2}", q)]
    if quotes and TRANSLATE.search(normalize(text)):
        return max(quotes, key=len)
    return None
