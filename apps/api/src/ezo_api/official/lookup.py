"""Finding the act a question names on LEX.UZ ("Mehnat kodeksi bo'yicha …",
"Davlat fuqarolik xizmati to'g'risidagi qonunda …").

The name is taken from the question's own words (Latin or Cyrillic), searched in LEX.UZ's
title search and matched against the base act: amendment laws ("… ўзгартириш ва қўшимчалар
киритиш тўғрисида"), approval laws and court decisions about one article are skipped, and an
act LEX.UZ marks as in force wins over one that lost force. Nothing is guessed: no match, no act.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ezo_api.core.text import normalize
from ezo_api.official.lexuz import LexUzConnector, SearchHit
from ezo_api.translation.translit import to_cyrillic

_W = r"[\w'ʻ‘’`ʼ-]+"
_CODE = re.compile(rf"((?:{_W}\s+){{0,4}}?)(kodeks|кодекс)\w*", re.IGNORECASE)
_LAW = re.compile(
    rf"((?:{_W}\s+){{1,7}}?)(to'g'risida|тўғрисида|haqida|ҳақида)\w*\s+(qonun|қонун)\w*",
    re.IGNORECASE,
)
_FILLER = frozenset(
    "menga bizga sizga bu shu ushbu o'sha qaysi qanday nima yangi amaldagi hozirgi "
    "ezo iltimos ayt aytib tushuntir bo'yicha boyicha uchun va yoki hamda "
    "ўзбекистон узбекистон o'zbekiston uzbekistan республикаси respublikasi "
    "республикасининг respublikasining".split()
)
_NOT_BASE = re.compile(
    r"ўзгартиш|ўзгартириш|қўшимча|тасдиқлаш|муносабати билан|моддас|амалга ошириш|"
    r"қўллаш|татбиқ|изоҳ|шарҳ"
)


@dataclass(frozen=True, slots=True)
class NamedAct:
    kind: str
    """"code" or "law"."""
    words: tuple[str, ...]
    """The name's words in the user's spelling, filler words removed."""

    def queries(self) -> list[str]:
        """Search texts, longest first (a leading stray word is dropped on each retry)."""
        out = []
        for start in range(len(self.words)):
            name = " ".join(self.words[start:])
            out.append(f"{name} кодекси" if self.kind == "code" else f"{name} тўғрисида")
        if self.kind == "code" and not out:
            return []
        return out[:3]


def named_act(text: str) -> NamedAct | None:
    norm = normalize(text)
    for kind, pattern in (("law", _LAW), ("code", _CODE)):
        found = pattern.search(norm)
        if not found:
            continue
        words = [w for w in found.group(1).split() if w.strip("'ʻ‘’`ʼ-") not in _FILLER]
        words = [w.rstrip(",.:;") for w in words if len(w) > 1]
        if kind == "code" and not words:
            continue
        if words:
            return NamedAct(kind, tuple(words[-6:]))
    return None


def _base_act(hit: SearchHit, kind: str) -> bool:
    title = hit.title.lower()
    if _NOT_BASE.search(title):
        return False
    return title.rstrip(' .»"').endswith("кодекси") if kind == "code" else "тўғрисида" in title


async def find_act(connector: LexUzConnector, client: Any, act: NamedAct) -> SearchHit | None:
    """The base act LEX.UZ lists for this name, in force first; None when nothing matches."""
    # Exact phrase first: a base act's title is buried under amendments and court decisions
    # in the newest-first plain search. Then the plain search for looser wording.
    attempts = [(q, True) for q in act.queries()[:2]] + [(act.queries()[0], False)]
    for query, exact in attempts:
        found = await connector.search(client, query, exact=exact)
        hits = [h for h in found if _base_act(h, act.kind)]
        want = to_cyrillic(query).lower()
        named = [h for h in hits if want in h.title.lower()]

        def rank(hit: SearchHit, want: str = want) -> tuple[bool, bool, int]:
            # The act whose own title IS the name (not a resolution quoting it) comes first,
            # then in force over lost force, then the shortest title.
            own = hit.title.lower().strip(' «»"').endswith(want)
            return (not own, hit.status != "in_force", len(hit.title))

        ranked = sorted(named or hits, key=rank)
        if ranked:
            return ranked[0]
    return None
