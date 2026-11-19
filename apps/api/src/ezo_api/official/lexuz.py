"""LEX.UZ — the National Database of Legislation of the Republic of Uzbekistan.

Access method: the public document pages (``https://lex.uz/docs/<id>`` in Uzbek,
``https://lex.uz/ru/docs/<id>`` in Russian) and the public title search
(``https://lex.uz/search/nat``), whose list marks each act in force or not. No official API
was found. Page and list markup were checked live on 2026-11-19 (`elements_text`,
`parse_search`); robots.txt has no rules and the owner reviewed the terms on that day.

Parsing stays conservative: the title, number and date come from the page ``<title>``, the
text from the page's document elements (editorial notes left out), and the status only from
an explicit label in the text or from LEX.UZ's own in-force mark in its list. Everything else
stays empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html import unescape
from typing import Any
from urllib.parse import urlencode

from ezo_api.knowledge.fetch import FetchedPage
from ezo_api.knowledge.parsers import ParseError
from ezo_api.knowledge.parsers.html import parse_html
from ezo_api.knowledge.parsers.text import decode_text
from ezo_api.official.base import (
    AccessReview,
    DocumentParseError,
    DocumentRef,
    OfficialSourceConnector,
    ParsedLegalDocument,
    SourcePolicy,
    UnsupportedSourceError,
)
from ezo_api.official.legal_text import explicit_status, mark_articles, parse_title, script_of
from ezo_api.translation.translit import to_cyrillic

_ID = re.compile(r"^\d{1,10}$")
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_SITE_SUFFIX = re.compile(r"\s*[|–—-]\s*(lex\.uz|LEX\.UZ).*$")
MIN_TEXT_CHARS = 80
# LEX.UZ document pages (checked live 2026-11-19): every heading, article and paragraph is a
# `<div class="KIND lx_elem">` whose text sits in `<div name="ID" id="ID">…</div>`. Editorial
# notes ("COMMENT", "INDEXES_ON_REF") are `lx_no_select` and are left out. Codes are several
# MB of HTML, so the text is cut out with this pattern instead of a general HTML parser.
_ELEMENT = re.compile(
    r'<div class="([A-Z_]+) lx_elem"[^>]*>.*?<div name="\d+" id="\d+">(.*?)</div></div>',
    re.DOTALL,
)
_HEADING_KINDS = {"TEXT_HEADER_DEFAULT": "## ", "CLAUSE_DEFAULT": "### "}
# Search results (checked live 2026-11-19): one `<tr class="dd-table__main-item">` per act,
# the act's state as `status_code_<letter>` (y: in force, r: lost force), its link and a
# badge with its type, date and number.
_ROW = re.compile(r'<tr class="dd-table__main-item">(.*?)</tr>', re.DOTALL)
_ROW_STATUS = re.compile(r"status_code_([a-z])")
_ROW_LINK = re.compile(r'href="/docs/(-?\d{1,10})"[^>]*>(.*?)</a>', re.DOTALL)
_ROW_BADGE = re.compile(r'badge-nine">(.*?)</span>', re.DOTALL)
LISTING_STATUS = {"y": "in_force", "r": "repealed"}

REVIEW = AccessReview(
    reviewed_on=date(2026, 11, 19),
    official_api="None found (web search 2026-10-18). Uses public document pages only.",
    robots_txt=(
        "Checked 2026-11-19: https://lex.uz/robots.txt redirects to the site's 404 page, so "
        "there are no robots rules. EZO still reads and obeys robots.txt on every run."
    ),
    terms_of_use=(
        "The owner reviewed the terms and enabled the connector on 2026-11-19. Official "
        "documents are not objects of copyright (see legal basis)."
    ),
    formats="HTML document pages (Uzbek: /docs/<id>, Russian: /ru/docs/<id>).",
    rate_limits=(
        "None published that could be found. EZO waits at least 5 s between requests, "
        "honours Crawl-delay and HTTP 429 Retry-After, and caps requests per run."
    ),
    legal_basis=(
        "Copyright law LRU-42 art. 8: official documents (laws, decisions) are not objects "
        "of copyright. Law LRU-682 on normative legal acts names the National Database of "
        "Legislation as an official publication source and lets electronic reference "
        "systems reproduce acts after official publication, with the source identified. "
        "(Read via secondary sources; confirm with the official texts.)"
    ),
    sources=(
        "https://lex.uz/docs/5695915",
        "https://lex.uz/docs/6123336",
        "https://github.com/LawCodex/uz",
        "https://github.com/javohirmat/uzbek-legal-corpus",
    ),
)

POLICY = SourcePolicy(
    key="lexuz",
    name="LEX.UZ",
    base_url="https://lex.uz",
    allowed_hosts=frozenset({"lex.uz", "www.lex.uz"}),
    access="public_web_pages",
    languages=("uz", "ru"),
    review=REVIEW,
    min_interval_seconds=5.0,
    supports_change_feed=False,
    notes=(
        "Reads the acts you name by LEX.UZ number, the ready-made core set for a hokimiyat, "
        "and any act a question names (found with LEX.UZ's title search), then re-checks "
        "them. It does not crawl the whole database."
    ),
)


def _clean(fragment: str) -> str:
    return " ".join(unescape(_TAGS.sub(" ", fragment)).split())


def elements_text(html: str) -> str:
    """The document text of a LEX.UZ page as Markdown-like lines (headings marked)."""
    lines: list[str] = []
    for kind, inner in _ELEMENT.findall(html):
        text = _clean(inner)
        if text:
            lines.append(_HEADING_KINDS.get(kind, "") + text)
    return "\n\n".join(lines)


@dataclass(frozen=True, slots=True)
class SearchHit:
    source_doc_id: str
    title: str
    status: str | None
    """in_force / repealed as LEX.UZ's list marks it; None when the mark is not one of those."""
    details: str
    """Type, date and number as LEX.UZ shows them ("Ўзбекистон Республикасининг Қонуни, …")."""


def parse_search(html: str) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for row in _ROW.findall(html):
        link = _ROW_LINK.search(row)
        if not link or link.group(1).startswith("-"):
            continue  # negative ids are departmental acts registered separately
        state = _ROW_STATUS.search(row)
        badge = _ROW_BADGE.search(row)
        hits.append(
            SearchHit(
                source_doc_id=link.group(1),
                title=_clean(link.group(2)),
                status=LISTING_STATUS.get(state.group(1)) if state else None,
                details=_clean(badge.group(1)) if badge else "",
            )
        )
    return hits


def search_url(title: str, *, exact: bool = False) -> str:
    """LEX.UZ title search in Uzbek Cyrillic (lang=3), the language its titles are kept in."""
    query = " ".join(to_cyrillic(title).split())[:100]
    params = {"searchtitle": query, "lang": "3"}
    if exact:
        params["exact2"] = "1"
    return "https://lex.uz/search/nat?" + urlencode(params)


class LexUzConnector(OfficialSourceConnector):
    policy = POLICY

    def validate_id(self, source_doc_id: str) -> str:
        value = str(source_doc_id).strip().lstrip("-")
        if not _ID.match(value):
            raise UnsupportedSourceError(
                f"“{source_doc_id}” is not a LEX.UZ document number (digits only)."
            )
        return value

    def document_url(self, ref: DocumentRef) -> str:
        doc_id = self.validate_id(ref.source_doc_id)
        if ref.language == "ru":
            return f"https://lex.uz/ru/docs/{doc_id}"
        if ref.language == "uz":
            return f"https://lex.uz/docs/{doc_id}"
        raise UnsupportedSourceError(
            f"LEX.UZ documents are available in uz and ru, not {ref.language}."
        )

    async def search(self, client: Any, title: str, *, exact: bool = False) -> list[SearchHit]:
        """Acts whose title contains `title` (Latin is converted to Cyrillic), newest first."""
        if len(title.strip()) < 3:
            return []
        page = await client.get(search_url(title, exact=exact))
        return parse_search(decode_text(page.data))

    async def listing_status(self, client: Any, parsed: ParsedLegalDocument) -> str | None:
        """LEX.UZ's own in-force mark for this act, from an exact title search (one request).
        The document page states no status; the search list does."""
        hits = await self.search(client, parsed.title, exact=True)
        for hit in hits:
            if hit.source_doc_id == parsed.source_doc_id:
                return hit.status
        return None

    def parse(self, page: FetchedPage, ref: DocumentRef) -> ParsedLegalDocument:
        html = decode_text(page.data)
        raw_title = ""
        for pattern in (_TITLE_TAG, _H1):
            match = pattern.search(html)
            if match and _clean(match.group(1)):
                raw_title = _SITE_SUFFIX.sub("", _clean(match.group(1)))
                break
        body = elements_text(html)
        fallback_title = ""
        if len(body) < MIN_TEXT_CHARS:
            try:
                parsed = parse_html(page.data, f"lexuz-{ref.source_doc_id}.html")
            except ParseError as exc:
                raise DocumentParseError(
                    f"No document text was found on the page ({exc.message})."
                ) from exc
            body, fallback_title = parsed.text.strip(), parsed.title or ""
        if len(body) < MIN_TEXT_CHARS:
            raise DocumentParseError("The page does not contain a document text.")
        info = parse_title(raw_title or fallback_title)
        status = explicit_status(body)
        warnings = []
        if not info.number:
            warnings.append("No document number found in the page title.")
        if status is None:
            warnings.append("The page states no status; EZO does not assume the act is in force.")
        title = info.title or raw_title or f"LEX.UZ {ref.source_doc_id}"
        return ParsedLegalDocument(
            source_doc_id=ref.source_doc_id,
            language=ref.language,
            title=title[:1000],
            text=f"# {title}\n\n{mark_articles(body)}",
            official_url=page.final_url or self.document_url(ref),
            script=script_of(body[:5_000]),
            document_number=info.number,
            document_type=info.document_type,
            authority=info.authority,
            adopted_on=info.adopted_on,
            status=status or "unknown",
            status_source="source_text" if status else "unverified",
            warnings=warnings,
        )
