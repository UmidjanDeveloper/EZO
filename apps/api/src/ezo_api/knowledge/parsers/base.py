"""Parser interface: bytes in, structured text out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ParseError(Exception):
    """The file could not be read. `message` is safe to show to the user."""

    def __init__(self, message: str, code: str = "parse_failed") -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(slots=True)
class Section:
    text: str
    page: int | None = None
    heading: str | None = None


@dataclass(slots=True)
class ParsedDocument:
    sections: list[Section]
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    needs_ocr: bool = False
    """True for scans/images: the file has (almost) no extractable text."""

    @property
    def text(self) -> str:
        return "\n\n".join(section.text for section in self.sections if section.text.strip())


class Parser(Protocol):
    def __call__(self, data: bytes, filename: str) -> ParsedDocument: ...


MAX_TABLE_ROWS = 20_000
