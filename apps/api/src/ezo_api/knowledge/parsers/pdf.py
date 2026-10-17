from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ezo_api.knowledge.parsers.base import ParsedDocument, ParseError, Section

MIN_CHARS_PER_PAGE = 10
"""Fewer extractable characters per page than this means the PDF is a scan."""


def parse_pdf(data: bytes, filename: str) -> ParsedDocument:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # pypdf raises several types here
                raise ParseError("The PDF is password-protected.") from exc
        sections = []
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            sections.append(Section(text=text, page=number))
        info = reader.metadata
        title = str(info.title).strip() if info and info.title else None
    except ParseError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise ParseError("The PDF could not be read (it may be damaged).") from exc

    pages = len(sections)
    chars = sum(len(s.text.strip()) for s in sections)
    return ParsedDocument(
        sections=sections,
        title=title,
        metadata={"pages": pages},
        needs_ocr=pages > 0 and chars < MIN_CHARS_PER_PAGE * pages,
    )
