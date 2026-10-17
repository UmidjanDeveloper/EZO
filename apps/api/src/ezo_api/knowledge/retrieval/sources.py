"""Source references: what EZO may cite, with full provenance."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SourceKind = Literal["file", "web_page", "web"]
EXCERPT_IN_METADATA = 400


@dataclass(slots=True)
class SourceRef:
    kind: SourceKind
    title: str
    excerpt: str
    source_name: str
    url: str | None = None
    date: str | None = None
    """ISO date: publication date for web results, indexing date for files."""
    document_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    revision_number: int | None = None
    chunk_id: uuid.UUID | None = None
    chunk_index: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    heading: str | None = None
    score: float = 0.0
    reliability: float = 0.5
    primary: bool = False
    n: int = 0
    """Citation number shown to the model and the user ([1], [2], ...)."""
    extra: dict[str, Any] = field(default_factory=dict)

    def location(self) -> str:
        parts: list[str] = []
        if self.page_start:
            pages = (
                f"p. {self.page_start}"
                if self.page_start == self.page_end or not self.page_end
                else f"pp. {self.page_start}-{self.page_end}"
            )
            parts.append(pages)
        if self.heading:
            parts.append(f"section “{self.heading}”")
        if self.revision_number:
            parts.append(f"revision {self.revision_number}")
        if self.chunk_index is not None:
            parts.append(f"chunk {self.chunk_index + 1}")
        return ", ".join(parts)

    def to_metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data["excerpt"] = self.excerpt[:EXCERPT_IN_METADATA]
        for key in ("document_id", "revision_id", "chunk_id"):
            if data[key] is not None:
                data[key] = str(data[key])
        data["location"] = self.location()
        return data


def number_sources(sources: list[SourceRef]) -> list[SourceRef]:
    for index, source in enumerate(sources, start=1):
        source.n = index
    return sources
