"""The organization's letterhead for documents outside the official catalog (reports,
notes, plans): logo, name lines, contacts and the standard formatting. Approved Word
templates are used for official document types only (`writing.render`)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ezo_api.core.text import normalize
from ezo_api.writing.service import OrgFacts

_ON_LETTERHEAD = re.compile(
    r"\b(blank\w*|tashkilot\w* (nomidan|uslubida|blankasida)|letterhead|"
    r"на бланке|фирменн\w* бланк\w*|от имени (нашей )?организаци\w*)"
)


def wants_letterhead(text: str) -> bool:
    """ "Tashkilotimiz blankasida …", "на бланке", "on our letterhead"."""
    return bool(_ON_LETTERHEAD.search(normalize(text)))


@dataclass(frozen=True, slots=True)
class Letterhead:
    lines: list[str]
    contacts: str = ""
    logo: bytes | None = None
    formatting: dict[str, Any] = field(default_factory=dict)
    name: str = ""


def from_facts(org: OrgFacts) -> Letterhead:
    lines = [ln.strip() for ln in (org.letterhead or "").splitlines() if ln.strip()] or [org.name]
    if not org.letterhead and org.department:
        lines.append(org.department)
    contacts = (
        ""
        if org.letterhead
        else " · ".join(v for v in (org.address, org.phone, org.email, org.website) if v)
    )
    return Letterhead(lines, contacts, org.logo, org.formatting, org.name)


_ORG_MENTION = re.compile(
    r"\b(tashkilot\w*|idoramiz\w*|muassasamiz\w*|our (organi[sz]ation|ministry|office)|"
    r"организаци\w*|нашего ведомства|нашей организац\w*)"
)


def mentions_organization(text: str) -> bool:
    """The request is about the user's organization (use its profile)."""
    return wants_letterhead(text) or bool(_ORG_MENTION.search(normalize(text)))
