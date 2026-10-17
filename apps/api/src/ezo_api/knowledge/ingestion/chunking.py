"""Split a parsed document into overlapping, citation-friendly chunks.

Chunks follow paragraph and sentence boundaries, never exceed `max_chars`, and
remember their page range and nearest heading so citations can point to them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.parsers.base import Section

TARGET_CHARS = 1_200
MAX_CHARS = 1_800
OVERLAP_CHARS = 150

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


@dataclass(slots=True)
class Chunk:
    index: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _Piece:
    text: str
    page: int | None
    heading: str | None


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split by sentences, then hard-split anything still too long."""
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def _pieces(sections: list[Section], max_chars: int) -> list[_Piece]:
    pieces: list[_Piece] = []
    for section in sections:
        text = normalize_text(section.text)
        for paragraph in text.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            for part in _split_long(paragraph, max_chars):
                pieces.append(_Piece(part, section.page, section.heading))
    return pieces


def _tail(text: str, size: int) -> str:
    if len(text) <= size:
        return text
    tail = text[-size:]
    space = tail.find(" ")
    return tail[space + 1 :] if 0 <= space < len(tail) - 1 else tail


def chunk_sections(
    sections: list[Section],
    target_chars: int = TARGET_CHARS,
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[_Piece] = []
    size = 0

    def emit() -> None:
        nonlocal buffer, size
        if not buffer:
            return
        body = "\n\n".join(piece.text for piece in buffer)
        pages = [piece.page for piece in buffer if piece.page is not None]
        headings = [piece.heading for piece in buffer if piece.heading]
        metadata: dict[str, Any] = {}
        if pages:
            metadata["page_start"], metadata["page_end"] = min(pages), max(pages)
        if headings:
            metadata["heading"] = headings[-1]
        if chunks and overlap_chars:
            body = _tail(chunks[-1].text, overlap_chars) + "\n\n" + body
            metadata["overlap"] = True
        chunks.append(Chunk(index=len(chunks), text=body, metadata=metadata))
        buffer, size = [], 0

    for piece in _pieces(sections, max_chars - overlap_chars - 2):
        if buffer and size + len(piece.text) > target_chars:
            emit()
        buffer.append(piece)
        size += len(piece.text) + 2
    emit()
    return chunks
