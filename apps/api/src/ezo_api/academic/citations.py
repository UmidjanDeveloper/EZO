"""Reference lists in APA 7, MLA 9, Chicago (author-date), Harvard, IEEE and GOST
(7.0.5-style), built only from metadata EZO actually has.

Nothing is filled in: a missing year is written the way each style writes an unknown
date ("n.d.", "s.a."), a missing author makes the title lead, and every reference keeps
the list of fields it lacks so the user can complete them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Style = Literal["apa", "mla", "chicago", "harvard", "ieee", "gost"]
STYLES: tuple[Style, ...] = ("apa", "mla", "chicago", "harvard", "ieee", "gost")
STYLE_NAMES = {
    "apa": "APA 7",
    "mla": "MLA 9",
    "chicago": "Chicago (author-date)",
    "harvard": "Harvard",
    "ieee": "IEEE",
    "gost": "GOST (7.0.5)",
}
_STYLE_WORDS = re.compile(r"\b(apa|mla|chicago|harvard|ieee|gost|гост)\b", re.IGNORECASE)
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_INITIALS = re.compile(r"^(?:[^\W\d_]{1,2}\.)+$")
Kind = Literal["article", "book", "chapter", "web", "thesis", "report"]


@dataclass(slots=True)
class Reference:
    title: str
    authors: list[str] = field(default_factory=list)
    """As written ("Karimov, Akmal" or "Akmal Karimov"); organisations as one name."""
    year: int | None = None
    kind: Kind = "article"
    container: str = ""
    """Journal, book (for a chapter) or website."""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    publisher: str = ""
    place: str = ""
    url: str = ""
    doi: str = ""
    accessed: str = ""
    """Date the web page was read (YYYY-MM-DD)."""

    def missing(self) -> list[str]:
        needed = ["authors", "year", "title"]
        if self.kind == "article":
            needed += ["container", "volume", "pages"]
        elif self.kind in ("book", "report", "thesis"):
            needed += ["publisher"]
        elif self.kind == "web":
            needed += ["url"]
        return [name for name in needed if not getattr(self, name)]


def style_from(text: str) -> Style | None:
    match = _STYLE_WORDS.search(text)
    if not match:
        return None
    word = match.group(1).lower()
    return "gost" if word == "гост" else word  # type: ignore[return-value]


def clean_doi(value: str) -> str:
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.IGNORECASE)
    return doi if _DOI.match(doi) else ""


def _split(name: str) -> tuple[str, list[str]]:
    """(family name, given names) of a person; organisations keep the whole name."""
    name = " ".join(name.split())
    if "," in name:
        family, given = name.split(",", 1)
        return family.strip(), given.split()
    parts = name.split(" ")
    if len(parts) == 1:
        return parts[0], []
    if all(_INITIALS.match(p) for p in parts[1:]):  # "Karimov A." / "Каримов А.Б."
        return parts[0], [i for p in parts[1:] for i in p.split(".") if i]
    return parts[-1], parts[:-1]


def _initials(given: list[str], spaced: bool = True) -> str:
    letters = [f"{g[0].upper()}." for g in given if g and g[0].isalpha()]
    return (" " if spaced else "").join(letters)


def _family_initials(name: str) -> str:
    family, given = _split(name)
    return f"{family}, {_initials(given)}".rstrip(", ") if given else family


def _initials_family(name: str) -> str:
    family, given = _split(name)
    return f"{_initials(given)} {family}".strip()


def _inverted(name: str) -> str:
    family, given = _split(name)
    return f"{family}, {' '.join(given)}".rstrip(", ") if given else family


def _join(names: list[str], last: str, *, comma_before_last: bool = True) -> str:
    if len(names) <= 1:
        return "".join(names)
    if len(names) == 2:
        return f"{names[0]}{',' if comma_before_last else ''} {last} {names[1]}"
    return ", ".join(names[:-1]) + f", {last} {names[-1]}"


def _end(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "?", "!")) else text + "."


def _link(ref: Reference) -> str:
    doi = clean_doi(ref.doi)
    return f"https://doi.org/{doi}" if doi else ref.url


def _pages(ref: Reference, prefix: str = "") -> str:
    return f"{prefix}{ref.pages.replace('-', '–')}" if ref.pages else ""


def apa(ref: Reference) -> str:
    names = [_family_initials(a) for a in ref.authors[:20]]
    authors = _join(names, "&") if names else ""
    date = f"({ref.year})." if ref.year else "(n.d.)."
    if ref.kind == "article":
        title = _end(ref.title)
        source = f"*{ref.container}*" if ref.container else ""
        if ref.volume:
            source += f", *{ref.volume}*" + (f"({ref.issue})" if ref.issue else "")
        if ref.pages:
            source += f", {_pages(ref)}"
        source = _end(source) if source else ""
    elif ref.kind == "chapter":
        title = _end(ref.title)
        source = f"In *{ref.container}*" + (f" (pp. {_pages(ref)})" if ref.pages else "") + "."
        source += f" {_end(ref.publisher)}" if ref.publisher else ""
    else:
        title = f"*{_end(ref.title)}*"
        tail = ref.container if ref.kind == "web" else ref.publisher
        source = _end(tail) if tail else ""
    parts = [_end(authors), date, title, source] if authors else [title, date, source]
    return " ".join(p for p in [*parts, _link(ref)] if p)


def mla(ref: Reference) -> str:
    if not ref.authors:
        authors = ""
    elif len(ref.authors) == 1:
        authors = _inverted(ref.authors[0])
    elif len(ref.authors) == 2:
        family, given = _split(ref.authors[1])
        authors = f"{_inverted(ref.authors[0])}, and {' '.join([*given, family])}"
    else:
        authors = f"{_inverted(ref.authors[0])}, et al"
    parts = [_end(authors)] if authors else []
    if ref.kind in ("article", "chapter", "web"):
        parts.append(f"“{_end(ref.title)}”")
        container = [f"*{ref.container}*"] if ref.container else []
        if ref.volume:
            container.append(f"vol. {ref.volume}")
        if ref.issue:
            container.append(f"no. {ref.issue}")
        if ref.publisher and ref.kind != "article":
            container.append(ref.publisher)
        if ref.year:
            container.append(str(ref.year))
        if ref.pages:
            container.append(_pages(ref, "pp. "))
        if container:
            parts.append(_end(", ".join(container)))
    else:
        parts.append(f"*{_end(ref.title)}*")
        tail = ", ".join(v for v in (ref.publisher, str(ref.year) if ref.year else "") if v)
        if tail:
            parts.append(_end(tail))
    link = _link(ref)
    if link:
        parts.append(_end(link.removeprefix("https://")))
    return " ".join(parts)


def chicago(ref: Reference) -> str:
    if not ref.authors:
        authors = ""
    elif len(ref.authors) == 1:
        authors = _inverted(ref.authors[0])
    else:
        rest = []
        for name in ref.authors[1:10]:
            family, given = _split(name)
            rest.append(" ".join([*given, family]))
        authors = _join([_inverted(ref.authors[0]), *rest], "and")
    year = f"{ref.year}." if ref.year else "n.d."
    lead = f"{_end(authors)} {year}" if authors else f"{_end(ref.title)} {year}"
    if ref.kind in ("article", "chapter", "web"):
        title = f"“{_end(ref.title)}”" if authors else ""
        source = f"*{ref.container}*" if ref.container else ""
        if ref.volume:
            source += f" {ref.volume}" + (f" ({ref.issue})" if ref.issue else "")
        if ref.pages:
            source += f": {_pages(ref)}"
        body = f"{title} {_end(source) if source else ''}"
    else:
        title = f"*{_end(ref.title)}*" if authors else ""
        place = ": ".join(v for v in (ref.place, ref.publisher) if v)
        body = f"{title} {_end(place) if place else ''}"
    return " ".join(f"{lead} {body} {_link(ref)}".split())


def harvard(ref: Reference) -> str:
    names = [_family_initials(a) for a in ref.authors[:10]]
    authors = _join(names, "and", comma_before_last=False) if names else ""
    year = f"({ref.year})" if ref.year else "(n.d.)"
    parts = [f"{authors} {year}" if authors else f"{ref.title} {year}"]
    if ref.kind in ("article", "chapter", "web"):
        source = f"*{ref.container}*" if ref.container else ""
        if ref.volume:
            source += f", {ref.volume}" + (f"({ref.issue})" if ref.issue else "")
        if ref.pages:
            source += f", {_pages(ref, 'pp. ')}"
        body = ", ".join(v for v in (f"‘{ref.title}’" if authors else "", source) if v)
    else:
        body = " ".join(v for v in (f"*{ref.title}*." if authors else "", ref.publisher) if v)
    text = " ".join(v for v in (parts[0], _end(body) if body else "") if v)
    link = _link(ref)
    if link:
        text = _end(text) if not body else text
        text += (
            f" Available at: {link}"
            + (f" (Accessed: {ref.accessed})" if ref.accessed else "")
            + "."
        )
    return " ".join(_end(text).split())


def ieee(ref: Reference, number: int) -> str:
    names = [_initials_family(a) for a in ref.authors[:6]]
    if len(ref.authors) > 6:
        names = [names[0] + " et al."]
    authors = _join(names, "and", comma_before_last=False) if names else ""
    parts = [f"[{number}]"]
    if authors:
        parts.append(authors + ",")
    if ref.kind in ("article", "chapter", "web"):
        parts.append(f"“{ref.title},”")
        details = [f"*{ref.container}*"] if ref.container else []
        if ref.volume:
            details.append(f"vol. {ref.volume}")
        if ref.issue:
            details.append(f"no. {ref.issue}")
        if ref.pages:
            details.append(_pages(ref, "pp. "))
        details.append(str(ref.year) if ref.year else "n.d.")
        parts.append(", ".join(details) + ("," if clean_doi(ref.doi) or ref.url else "."))
    else:
        parts.append(f"*{ref.title}*.")
        tail = ", ".join(
            v for v in (ref.place, ref.publisher, str(ref.year) if ref.year else "") if v
        )
        if tail:
            parts.append(_end(tail))
    doi = clean_doi(ref.doi)
    if doi:
        parts.append(f"doi: {doi}.")
    elif ref.url:
        parts.append(f"[Online]. Available: {ref.url}")
    return " ".join(parts)


def _dash(text: str, part: str) -> str:
    """GOST's ". — " separator without doubling a final full stop."""
    return f"{text.rstrip('.')}. — {part}"


def gost(ref: Reference) -> str:
    first = ""
    if ref.authors:
        family, given = _split(ref.authors[0])
        first = f"{family} {_initials(given, spaced=False)}".strip()
    others = ", ".join(_initials_family(a) for a in ref.authors[:4])
    text = f"{first} {ref.title}" if first else ref.title
    if others:
        text += f" / {others}"
    year = str(ref.year) if ref.year else "s.a."
    if ref.kind in ("article", "chapter") and ref.container:
        text = _dash(f"{text} // {ref.container}", year)
        if ref.volume:
            text = _dash(text, f"Vol. {ref.volume}")
        if ref.issue:
            text += f", № {ref.issue}"
        if ref.pages:
            text = _dash(text, f"P. {_pages(ref)}")
    elif ref.kind == "web":
        text += " [Electronic resource]"
        if ref.container:
            text += f" // {ref.container}"
        text = _dash(text, year)
    else:
        place = " : ".join(v for v in (ref.place, ref.publisher) if v)
        text = _dash(text, f"{place}, {year}" if place else year)
    doi = clean_doi(ref.doi)
    if doi:
        text = _dash(text, f"DOI: {doi}")
    elif ref.url:
        text = _dash(
            text, f"URL: {ref.url}" + (f" (accessed: {ref.accessed})" if ref.accessed else "")
        )
    return _end(text)


def _sort_key(ref: Reference) -> tuple[str, int]:
    lead = _split(ref.authors[0])[0] if ref.authors else ref.title
    return (lead.lower(), ref.year or 0)


def format_list(references: list[Reference], style: Style) -> list[str]:
    """Formatted entries in the style's order (IEEE and GOST: numbered as given; the
    author-date styles: alphabetical)."""
    if style == "ieee":
        return [ieee(ref, n) for n, ref in enumerate(references, start=1)]
    if style == "gost":  # numbered in citation order, so [n] in the text matches the list
        return [f"{n}. {gost(ref)}" for n, ref in enumerate(references, start=1)]
    formatter = {"apa": apa, "mla": mla, "chicago": chicago, "harvard": harvard, "gost": gost}[
        style
    ]
    return [formatter(ref) for ref in sorted(references, key=_sort_key)]


def in_text(ref: Reference, style: Style, number: int) -> str:
    """How the reference is cited in the text."""
    if style in ("ieee", "gost"):
        return f"[{number}]"
    names = [_split(a)[0] for a in ref.authors]
    joiner = "&" if style == "apa" else "and"
    if not names:
        who = f"“{ref.title[:40]}”"
    elif len(names) == 1:
        who = names[0]
    elif len(names) == 2:
        who = f"{names[0]} {joiner} {names[1]}"
    else:
        who = f"{names[0]} et al."
    if style == "mla":
        return f"({who})"
    year = str(ref.year) if ref.year else "n.d."
    return f"({who}, {year})" if style in ("apa", "harvard") else f"({who} {year})"
