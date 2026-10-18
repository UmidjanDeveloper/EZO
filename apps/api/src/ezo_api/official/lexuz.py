"""LEX.UZ — the National Database of Legislation of the Republic of Uzbekistan.

Proof-of-concept connector. Access method: the public document pages
(``https://lex.uz/docs/<id>`` in Uzbek, ``https://lex.uz/ru/docs/<id>`` in Russian).
No official API was found. The URL pattern and the page-title format
(``LRU-682-сон 20.04.2021. On normative legal acts``) are documented in public
sources (see `REVIEW.sources`). robots.txt and the site's terms could NOT be read
from EZO's build environment (the host was unreachable), so the owner must review
them before enabling this connector (``EZO_OFFICIAL_SOURCES=lexuz``).

Parsing is deliberately conservative because the live markup was not available
for verification: the title comes from the page ``<title>`` (or the main heading),
the body from main-content extraction, number/type/date from the title, and the
status only from an explicit status label. Everything else stays empty.
"""

from __future__ import annotations

import re
from datetime import date
from html import unescape

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

_ID = re.compile(r"^\d{1,10}$")
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_SITE_SUFFIX = re.compile(r"\s*[|–—-]\s*(lex\.uz|LEX\.UZ).*$")
MIN_TEXT_CHARS = 80

REVIEW = AccessReview(
    reviewed_on=date(2026, 10, 18),
    official_api="None found (web search 2026-10-18). Uses public document pages only.",
    robots_txt=(
        "Not verified: lex.uz was unreachable from EZO's build environment. EZO reads and "
        "obeys robots.txt at run time and does not fetch if it cannot read it."
    ),
    terms_of_use=(
        "Not verified. A third-party project states the terms do not restrict reuse; the "
        "owner must confirm on lex.uz before enabling."
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
        "Proof of concept. Tracks documents you name by their LEX.UZ ID and re-checks them; "
        "discovering new acts automatically needs a verified feed or API."
    ),
)


def _clean(fragment: str) -> str:
    return " ".join(unescape(_TAGS.sub(" ", fragment)).split())


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

    def parse(self, page: FetchedPage, ref: DocumentRef) -> ParsedLegalDocument:
        html = decode_text(page.data)
        raw_title = ""
        for pattern in (_TITLE_TAG, _H1):
            match = pattern.search(html)
            if match and _clean(match.group(1)):
                raw_title = _SITE_SUFFIX.sub("", _clean(match.group(1)))
                break
        try:
            parsed = parse_html(page.data, f"lexuz-{ref.source_doc_id}.html")
        except ParseError as exc:
            raise DocumentParseError(
                f"No document text was found on the page ({exc.message})."
            ) from exc
        body = parsed.text.strip()
        if len(body) < MIN_TEXT_CHARS:
            raise DocumentParseError("The page does not contain a document text.")
        info = parse_title(raw_title or parsed.title or "")
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
