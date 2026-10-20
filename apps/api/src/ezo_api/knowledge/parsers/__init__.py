"""Format-specific parsers. Add a format by registering it in PARSERS."""

from __future__ import annotations

from ezo_api.documents.isolation import ISOLATION_MESSAGE, native_fixtures_allowed
from ezo_api.knowledge.parsers.base import ParsedDocument, ParseError, Parser, Section
from ezo_api.knowledge.parsers.html import parse_html
from ezo_api.knowledge.parsers.image import parse_image
from ezo_api.knowledge.parsers.office import parse_docx, parse_xlsx
from ezo_api.knowledge.parsers.pdf import parse_pdf
from ezo_api.knowledge.parsers.text import parse_csv, parse_markdown, parse_text

PARSERS: dict[str, Parser] = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "xlsx": parse_xlsx,
    "csv": parse_csv,
    "text": parse_text,
    "markdown": parse_markdown,
    "html": parse_html,
    "image": parse_image,
}


def parse(category: str, data: bytes, filename: str) -> ParsedDocument:
    if category not in ("text", "markdown", "csv") and not native_fixtures_allowed():
        raise ParseError(ISOLATION_MESSAGE, "isolation_unavailable")
    parser = PARSERS.get(category)
    if parser is None:
        raise ParseError(f"No parser for '{category}' files.")
    return parser(data, filename)


__all__ = ["PARSERS", "ParseError", "ParsedDocument", "Section", "parse"]
