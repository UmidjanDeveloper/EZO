"""Shared types for reading a source: limits, the running budget and what was read."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class Limits(BaseModel):
    """How much of a source EZO may read in one run (the owner can lower or raise them
    within the hard caps)."""

    max_pages: int = Field(default=25, ge=1, le=200)
    """Websites: pages; repositories: files; packages: documents."""
    max_depth: int = Field(default=2, ge=0, le=4)
    """Websites: link depth from the start page."""
    max_total_mb: float = Field(default=20, gt=0, le=100)
    max_file_kb: int = Field(default=512, ge=16, le=5_000)
    """Repository and package files larger than this are skipped."""
    max_seconds: int = Field(default=300, ge=10, le=1_800)
    min_interval_seconds: float = Field(default=1.0, ge=0, le=30)
    """Politeness delay between two requests to the same host (robots Crawl-delay wins
    when longer)."""
    include_code: bool = True
    """Repositories: also read entry points and examples (never executed)."""


@dataclass(slots=True)
class Budget:
    limits: Limits
    started: float = field(default_factory=time.monotonic)
    documents: int = 0
    bytes: int = 0
    requests: int = 0

    def over(self) -> str | None:
        """Why reading must stop now, or None."""
        if self.documents >= self.limits.max_pages:
            return "page_limit"
        if self.bytes >= self.limits.max_total_mb * 1024 * 1024:
            return "size_limit"
        if time.monotonic() - self.started >= self.limits.max_seconds:
            return "time_limit"
        return None


@dataclass(slots=True)
class ReadDocument:
    """One document read from the source, ready for the knowledge pipeline."""

    url: str
    title: str
    filename: str
    category: str
    """html | pdf | text | markdown (parser category)."""
    data: bytes
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Inspection:
    """What discovery and reading produced. Problems are recorded, never hidden."""

    title: str
    profile: dict[str, Any] = field(default_factory=dict)
    version: str | None = None
    license: str | None = None
    documents: list[ReadDocument] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    """{"url", "reason"} for pages or files not read (robots, type, size, error)."""
    stopped: str | None = None
    """A budget limit that ended the reading early."""
    errors: list[str] = field(default_factory=list)

    def skip(self, url: str, reason: str) -> None:
        if len(self.skipped) < 200:
            self.skipped.append({"url": url, "reason": reason})
