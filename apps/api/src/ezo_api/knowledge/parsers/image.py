"""Images: stored as-is. Text extraction needs OCR (OCR arrives in ROADMAP Phase 6.5)."""

from __future__ import annotations

from ezo_api.knowledge.parsers.base import ParsedDocument


def parse_image(data: bytes, filename: str) -> ParsedDocument:
    return ParsedDocument(sections=[], metadata={"format": "image"}, needs_ocr=True)
