"""Terminology memory: which of the user's terms apply to a text, and checking that a
translation used them.

Matching tolerates word endings (Uzbek and Russian inflect: "hokimlik" also matches
"hokimligiga", "администрация" matches "администрации") and the Uzbek script (Latin and
Cyrillic forms match each other).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.text import normalize, quoted
from ezo_api.db.models import GlossaryTerm
from ezo_api.translation.languages import base
from ezo_api.translation.translit import to_latin

MAX_PROMPT_TERMS = 80
_WORD = re.compile(r"[\w']+", re.UNICODE)
_ADD = re.compile(
    r"\b(glossari\w*|lug'at\w*|atama\w*|termin\w*|glossary|глоссари\w*|словар\w*|термин\w*)"
)
_ADD_VERB = re.compile(
    r"\b(qo'sh|saqla|eslab qol|yodda tut|add|save|remember|добав|сохран|запомни)"
)
_PAIR = re.compile(r"[:\n]\s*(.{1,150}?)\s*(?:=|→|->|—|–| - )\s*(.{1,150}?)\s*$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Term:
    source: str
    target: str
    note: str | None = None
    organization: bool = False


def _comparable(text: str, language: str) -> list[str]:
    norm = normalize(to_latin(text) if base(language) == "uz" else text)
    return [w.strip("'") for w in _WORD.findall(norm) if w.strip("'")]


def _stem(word: str) -> str:
    return word if len(word) <= 5 else word[: max(4, len(word) - 2)]


def occurs(term: str, text_words: list[str], language: str) -> bool:
    """Whether `term` occurs in a text (given as `_comparable` words), endings allowed."""
    wanted = [_stem(w) for w in _comparable(term, language)]
    if not wanted:
        return False
    size = len(wanted)
    return any(
        all(text_words[i + k].startswith(wanted[k]) for k in range(size))
        for i in range(len(text_words) - size + 1)
    )


def relevant(terms: list[Term], text: str, source_language: str) -> list[Term]:
    words = _comparable(text, source_language)
    seen: set[str] = set()
    found: list[Term] = []
    for term in terms:  # organization terms come first and win
        key = normalize(term.source)
        if key not in seen and occurs(term.source, words, source_language):
            seen.add(key)
            found.append(term)
    return found[:MAX_PROMPT_TERMS]


def missing_in(
    terms: list[Term], source: str, target: str, source_language: str, target_language: str
) -> list[Term]:
    """Terms that occur in the source but whose required translation is not in the target."""
    target_words = _comparable(target, target_language)
    return [
        t
        for t in relevant(terms, source, source_language)
        if not occurs(t.target, target_words, target_language)
    ]


def prompt_block(terms: list[Term], target_language: str) -> str:
    if not terms:
        return ""
    lines = []
    for term in terms:
        target = to_latin(term.target) if target_language == "uz" else term.target
        note = f" ({term.note})" if term.note else ""
        lines.append(f"- “{term.source}” → “{target}”{note}")
    return (
        "Required terminology (the user's glossary; use exactly these translations, "
        "inflected as the grammar needs):\n" + "\n".join(lines)
    )


async def load_terms(
    session: AsyncSession,
    user_id: uuid.UUID,
    source_language: str,
    target_language: str,
    organization_id: uuid.UUID | None = None,
) -> list[Term]:
    """The user's terms for this language pair (also entries stored the other way round).
    Terms of `organization_id` come first; other organizations' terms are not used."""
    src, tgt = base(source_language), base(target_language)
    rows = (
        await session.scalars(
            select(GlossaryTerm).where(
                GlossaryTerm.user_id == user_id,
                or_(
                    GlossaryTerm.organization_id.is_(None),
                    GlossaryTerm.organization_id == organization_id,
                ),
                or_(
                    (GlossaryTerm.source_language == src) & (GlossaryTerm.target_language == tgt),
                    (GlossaryTerm.source_language == tgt) & (GlossaryTerm.target_language == src),
                ),
            )
        )
    ).all()
    terms: list[tuple[int, Term]] = []
    for row in rows:
        forward = row.source_language == src
        rank = 0 if row.organization_id is not None else 1
        terms.append(
            (
                rank if forward else rank + 2,
                Term(
                    source=row.source_term if forward else row.target_term,
                    target=row.target_term if forward else row.source_term,
                    note=row.note,
                    organization=row.organization_id is not None,
                ),
            )
        )
    return [t for _, t in sorted(terms, key=lambda item: item[0])]


def add_request(text: str) -> tuple[str, str] | None:
    """(source term, target term) from "Glossariyga qo'sh: «hokimlik» → «khokimiyat»"."""
    norm = normalize(text)
    if not (_ADD.search(norm) and _ADD_VERB.search(norm)):
        return None
    quotes = quoted(text)
    if len(quotes) >= 2:
        return quotes[0].strip(), quotes[1].strip()
    match = _PAIR.search(text.strip())
    if match:
        return match.group(1).strip(" «»\"'“”"), match.group(2).strip(" «»\"'“”.")
    return None
