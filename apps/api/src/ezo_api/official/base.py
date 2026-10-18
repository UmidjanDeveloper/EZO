"""The OfficialSourceConnector interface and its access policy.

A connector knows one official source: which hosts it may contact, how a stable
document ID becomes an official URL, and how a fetched page becomes a
`ParsedLegalDocument`. It never fetches by itself — all traffic goes through
`OfficialHttpClient`, which enforces robots.txt, rate limits and access refusals.

Every connector carries an `AccessReview`: what was verified about the source
(official API, robots.txt, terms, formats, rate limits, legal basis) and when.
A connector whose access method is not verified cannot be enabled.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from ezo_api.knowledge.fetch import FetchedPage

AccessMethod = Literal["public_web_pages", "official_api", "unverified"]


class OfficialSourceError(Exception):
    """Base error; `message` is safe to show."""

    code = "official_source_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class UnsupportedSourceError(OfficialSourceError):
    code = "unsupported_source"


class SourceNotEnabledError(OfficialSourceError):
    code = "source_not_enabled"


class AccessRestrictedError(OfficialSourceError):
    """The source refused access (401/403/451) or robots.txt forbids the page. Never bypassed."""

    code = "access_restricted"


class RobotsUnavailableError(OfficialSourceError):
    """robots.txt could not be read (5xx, network): EZO does not fetch (fail closed)."""

    code = "robots_unavailable"


class RateLimitedError(OfficialSourceError):
    code = "rate_limited"

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TemporaryFetchError(OfficialSourceError):
    code = "temporary"


class BudgetExhaustedError(OfficialSourceError):
    code = "budget_exhausted"


class DocumentParseError(OfficialSourceError):
    code = "parse_error"


@dataclass(frozen=True, slots=True)
class AccessReview:
    """What is known about permitted access, with honest "not verified" entries."""

    reviewed_on: date
    official_api: str
    robots_txt: str
    terms_of_use: str
    formats: str
    rate_limits: str
    legal_basis: str
    sources: tuple[str, ...] = ()
    """URLs the review relied on."""


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    key: str
    name: str
    base_url: str
    allowed_hosts: frozenset[str]
    access: AccessMethod
    languages: tuple[str, ...]
    review: AccessReview
    min_interval_seconds: float = 5.0
    """Floor for the delay between two requests to this source (settings can only raise it)."""
    supports_change_feed: bool = False
    notes: str = ""

    @property
    def can_be_enabled(self) -> bool:
        return self.access != "unverified"


@dataclass(frozen=True, slots=True)
class DocumentRef:
    source_doc_id: str
    language: str


@dataclass(slots=True)
class ParsedLegalDocument:
    source_doc_id: str
    language: str
    title: str
    text: str
    """Markdown: one `##` section per article where articles can be recognised."""
    official_url: str
    script: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    authority: str | None = None
    adopted_on: date | None = None
    published_on: date | None = None
    effective_on: date | None = None
    status: str = "unknown"
    status_source: str = "unverified"
    revision_label: str | None = None
    warnings: list[str] = field(default_factory=list)


class OfficialSourceConnector(ABC):
    policy: SourcePolicy

    @abstractmethod
    def validate_id(self, source_doc_id: str) -> str:
        """The normalized ID, or `UnsupportedSourceError` (never build URLs from junk)."""

    @abstractmethod
    def document_url(self, ref: DocumentRef) -> str:
        """The official public URL of one document in one language."""

    @abstractmethod
    def parse(self, page: FetchedPage, ref: DocumentRef) -> ParsedLegalDocument:
        """Turn a fetched page into a document. Raise `DocumentParseError` when it is not one."""

    def changed_since(self) -> None:
        """Discovering new or changed documents needs a verified change feed or API."""
        raise UnsupportedSourceError(
            f"{self.policy.name} has no verified change feed; EZO re-checks the documents "
            "you track instead."
        )
