"""Long documents: split by their own structure, processed part by part.

A long text is cut at its headings (Markdown headings, "1.2.", "5-modda", "II bob",
"Статья 5", "Глава 2", "Article 3", short ALL-CAPS lines) and, where a section is still
too long, at paragraph boundaries. Every part keeps the titles of the sections it
belongs to, so a summary or an answer can say where something comes from.

Nothing is cut silently: callers get every part, and the limit for one request
(`MAX_TOTAL_CHARS`) is enforced with an explicit error.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

PART_CHARS = 12_000
MAX_TOTAL_CHARS = 2_000_000
"""About 800 pages; longer texts are refused with an explanation, not shortened."""

_HEADINGS = [
    re.compile(r"^\s{0,3}#{1,6}\s+\S"),
    re.compile(r"^\s*\d{1,3}(\.\d{1,3}){0,4}\.?\s+[^\d\s].{0,150}$"),
    re.compile(r"^\s*\d{1,4}\s*-\s*(modda|bob|bo'lim|bo‘lim|qism|band)\b", re.IGNORECASE),
    re.compile(r"^\s*[IVXLC]{1,6}\.?\s+(bob|bo'lim|bo‘lim|qism|глава|раздел)\b", re.IGNORECASE),
    re.compile(
        r"^\s*(modda|bob|bo'lim|qism|статья|глава|раздел|часть|article|chapter|section|part)"
        r"\s+[\dIVXLC]{1,6}\b",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True, slots=True)
class Part:
    index: int
    text: str
    titles: tuple[str, ...]
    """Headings of the sections in this part (first one is where it starts)."""

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def label(self) -> str:
        if not self.titles:
            return f"part {self.index + 1}"
        first = self.titles[0][:80]
        return first if len(self.titles) == 1 else f"{first} … {self.titles[-1][:60]}"


class TooLongError(Exception):
    def __init__(self, chars: int) -> None:
        self.chars = chars
        super().__init__(f"{chars} characters")


def is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 160:
        return False
    if any(p.match(stripped) for p in _HEADINGS):
        return True
    letters = [c for c in stripped if c.isalpha()]
    return len(letters) >= 4 and len(stripped) <= 80 and all(c.isupper() for c in letters)


def sections(text: str) -> list[tuple[str, str]]:
    """(title, body) pairs in document order; text before the first heading has title ""."""
    result: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if is_heading(line):
            result.append((line.strip().lstrip("#").strip(), [line]))
        else:
            result[-1][1].append(line)
    return [
        (title, "\n".join(lines).strip()) for title, lines in result if "\n".join(lines).strip()
    ]


def _paragraph_pieces(body: str, limit: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", body):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        while len(paragraph) > limit:  # one enormous paragraph: cut at a sentence end
            cut = max(paragraph.rfind(". ", 0, limit), paragraph.rfind("\n", 0, limit))
            cut = cut + 1 if cut > limit // 2 else limit
            if current:
                pieces.append(current)
                current = ""
            pieces.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if current and len(current) + len(paragraph) + 2 > limit:
            pieces.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        pieces.append(current)
    return pieces


def split_parts(text: str, limit: int = PART_CHARS) -> list[Part]:
    """Parts of at most `limit` characters that follow the document's sections."""
    if len(text) > MAX_TOTAL_CHARS:
        raise TooLongError(len(text))
    parts: list[Part] = []
    buffer: list[str] = []
    titles: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal buffer, titles, size
        if buffer:
            parts.append(Part(len(parts), "\n\n".join(buffer), tuple(titles)))
        buffer, titles, size = [], [], 0

    for title, body in sections(text):
        if len(body) > limit:
            flush()
            for piece in _paragraph_pieces(body, limit):
                parts.append(Part(len(parts), piece, (title,) if title else ()))
            continue
        if size and size + len(body) + 2 > limit:
            flush()
        buffer.append(body)
        if title:
            titles.append(title)
        size += len(body) + 2
    flush()
    return parts


def outline(text: str, limit: int = 60) -> list[str]:
    """The document's headings (for a table of contents in replies)."""
    return [title for title, _ in sections(text) if title][:limit]
