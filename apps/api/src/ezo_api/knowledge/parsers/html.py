"""Web pages: main-content extraction with trafilatura (drops menus, ads, footers)."""

from __future__ import annotations

import json

import trafilatura

from ezo_api.knowledge.parsers.base import ParsedDocument, ParseError, Section
from ezo_api.knowledge.parsers.text import decode_text


def parse_html(data: bytes, filename: str) -> ParsedDocument:
    html = decode_text(data)
    result = trafilatura.extract(
        html, output_format="json", with_metadata=True, include_tables=True, favor_precision=True
    )
    if not result:
        raise ParseError("No readable text was found on the web page.")
    payload = json.loads(result)
    text = (payload.get("text") or "").strip()
    if not text:
        raise ParseError("No readable text was found on the web page.")
    metadata = {
        key: payload[key]
        for key in ("author", "date", "sitename", "hostname", "description")
        if payload.get(key)
    }
    return ParsedDocument(
        sections=[Section(text=text)], title=payload.get("title"), metadata=metadata
    )
