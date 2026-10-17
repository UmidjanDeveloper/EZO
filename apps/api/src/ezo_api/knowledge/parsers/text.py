"""Plain text, Markdown and CSV parsers."""

from __future__ import annotations

import csv
import io
import re

from ezo_api.knowledge.parsers.base import MAX_TABLE_ROWS, ParsedDocument, Section

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_text(data: bytes, filename: str) -> ParsedDocument:
    return ParsedDocument(sections=[Section(text=decode_text(data))])


def parse_markdown(data: bytes, filename: str) -> ParsedDocument:
    text = decode_text(data)
    sections: list[Section] = []
    heading: str | None = None
    title: str | None = None
    current: list[str] = []
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            if current:
                sections.append(Section(text="\n".join(current).strip(), heading=heading))
                current = []
            heading = match.group(2)
            if title is None and len(match.group(1)) == 1:
                title = heading
        current.append(line)
    if current:
        sections.append(Section(text="\n".join(current).strip(), heading=heading))
    return ParsedDocument(sections=sections, title=title, metadata={"format": "markdown"})


def parse_csv(data: bytes, filename: str) -> ParsedDocument:
    text = decode_text(data)
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(text[:4096], ",;\t|")
    except csv.Error:
        dialect = csv.excel
    lines: list[str] = []
    truncated = False
    for index, row in enumerate(csv.reader(io.StringIO(text), dialect)):
        if index >= MAX_TABLE_ROWS:
            truncated = True
            break
        if any(cell.strip() for cell in row):
            lines.append(" | ".join(cell.strip() for cell in row))
    return ParsedDocument(
        sections=[Section(text="\n".join(lines))],
        metadata={"format": "csv", "rows": len(lines), "truncated": truncated},
    )
