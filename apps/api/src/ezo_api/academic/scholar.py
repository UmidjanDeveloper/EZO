"""Scholarly literature search through OpenAlex (https://openalex.org): a free, open index
of research works with real metadata (authors, year, venue, DOI, citation counts).

Requests go through `SafeFetcher.fetch_json` (SSRF protection, size limit, JSON only).
Results are used as they come: EZO never adds a work, an author or a DOI that OpenAlex
did not return. Disable with EZO_SCHOLAR_PROVIDER=none.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

from ezo_api.academic.citations import Kind, Reference, clean_doi
from ezo_api.knowledge.fetch import FetchError, SafeFetcher

API = "https://api.openalex.org/works"
FIELDS = (
    "id,doi,display_name,publication_year,type,authorships,primary_location,biblio,"
    "cited_by_count,open_access,abstract_inverted_index,language"
)
_KINDS: dict[str, Kind] = {
    "article": "article",
    "review": "article",
    "book": "book",
    "book-chapter": "chapter",
    "dissertation": "thesis",
    "report": "report",
}


class ScholarError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(slots=True)
class Work:
    reference: Reference
    openalex_id: str
    cited_by: int
    open_access_url: str
    abstract: str
    language: str


def _abstract(index: dict[str, list[int]] | None, limit: int = 1_500) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the text."""
    if not index:
        return ""
    words: dict[int, str] = {}
    for word, positions in index.items():
        for position in positions:
            words[position] = word
    return " ".join(words[i] for i in sorted(words))[:limit]


def parse_work(item: dict[str, Any]) -> Work | None:
    title = str(item.get("display_name") or item.get("title") or "").strip()
    if not title:
        return None
    biblio = item.get("biblio") or {}
    first, last = biblio.get("first_page"), biblio.get("last_page")
    pages = f"{first}-{last}" if first and last and first != last else str(first or "")
    location = item.get("primary_location") or {}
    source = location.get("source") or {}
    authors = [
        str((a.get("author") or {}).get("display_name") or "").strip()
        for a in item.get("authorships") or []
    ]
    reference = Reference(
        title=title,
        authors=[a for a in authors if a][:30],
        year=item.get("publication_year")
        if isinstance(item.get("publication_year"), int)
        else None,
        kind=_KINDS.get(str(item.get("type") or ""), "article"),
        container=str(source.get("display_name") or ""),
        volume=str(biblio.get("volume") or ""),
        issue=str(biblio.get("issue") or ""),
        pages=pages,
        url=str(location.get("landing_page_url") or ""),
        doi=clean_doi(str(item.get("doi") or "")),
    )
    return Work(
        reference=reference,
        openalex_id=str(item.get("id") or ""),
        cited_by=int(item.get("cited_by_count") or 0),
        open_access_url=str((item.get("open_access") or {}).get("oa_url") or ""),
        abstract=_abstract(item.get("abstract_inverted_index")),
        language=str(item.get("language") or ""),
    )


class ScholarSearch(Protocol):
    name: str

    async def search(
        self, query: str, limit: int = 10, from_year: int | None = None
    ) -> list[Work]: ...


class OpenAlexClient:
    name = "openalex"

    def __init__(self, fetcher: SafeFetcher, mailto: str = "") -> None:
        self.fetcher = fetcher
        self.mailto = mailto

    def url(self, query: str, limit: int, from_year: int | None) -> str:
        params: dict[str, str | int] = {"search": query[:300], "per-page": max(1, min(25, limit))}
        params["select"] = FIELDS
        if from_year:
            params["filter"] = f"from_publication_date:{from_year}-01-01"
        if self.mailto:
            params["mailto"] = self.mailto
        return f"{API}?{urlencode(params)}"

    async def search(self, query: str, limit: int = 10, from_year: int | None = None) -> list[Work]:
        try:
            page = await self.fetcher.fetch_json(self.url(query, limit, from_year))
            data = json.loads(page.data)
        except FetchError as exc:
            raise ScholarError(f"OpenAlex could not be reached: {exc.message}") from exc
        except ValueError as exc:
            raise ScholarError("OpenAlex returned an unreadable answer.") from exc
        works = [parse_work(item) for item in data.get("results") or [] if isinstance(item, dict)]
        return [w for w in works if w is not None]
