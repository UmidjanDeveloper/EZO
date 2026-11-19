# ruff: noqa: E501
"""A table to analyse, from an uploaded file — without opening the workbook in the API.

- CSV: plain text, read here with the csv module.
- XLSX: the text the isolated document worker (or the ingestion parser) already extracted:
  one line per row, cells joined by " | ", one block per sheet. EZO never opens the
  uploaded workbook in the API process (F20).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import DocumentRevision, KnowledgeDocument
from ezo_api.knowledge.parsers.text import decode_text

MAX_ROWS = 20_000
CSV_MIMES = ("text/csv", "application/csv")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TableError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(slots=True)
class Table:
    name: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False
    notes: list[str] = field(default_factory=list)


_NUMBER = re.compile(r"^[+-]?(\d{1,3}([  ,]\d{3})+|\d+)([.,]\d+)?%?$")


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value or "").strip().replace(" ", " ")
    if not text or not _NUMBER.match(text):
        return None
    percent = text.endswith("%")
    text = text.rstrip("%")
    # "1 234,5" / "1,234.5" / "1234,5"
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        head, _, tail = text.rpartition(",")
        text = (
            text.replace(",", "") if len(tail) == 3 and head else head.replace(" ", "") + "." + tail
        )
    text = text.replace(" ", "")
    try:
        return float(text) / (100 if percent else 1)
    except ValueError:
        return None


_MONTHS = {
    # uz / ru / en month names → number
    **{
        m: i
        for i, m in enumerate(
            ("yanvar fevral mart aprel may iyun iyul avgust sentabr oktabr noyabr dekabr").split(),
            1,
        )
    },
    **{
        m: i
        for i, m in enumerate(
            ("январ феврал март апрел ма июн июл август сентябр октябр ноябр декабр").split(), 1
        )
    },
    **{
        m: i
        for i, m in enumerate(
            (
                "january february march april may june july august september october november december"
            ).split(),
            1,
        )
    },
}


def to_period(value: Any) -> date | None:
    """A date-like cell (2026-03-01, 01.03.2026, 2026-03, "mart 2026", 2026) → a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return None
    for pattern, order in (
        (r"^(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"),
        (r"^(\d{1,2})[./](\d{1,2})[./](\d{4})", "dmy"),
        (r"^(\d{4})[-./](\d{1,2})$", "ym"),
        (r"^(\d{1,2})[-./](\d{4})$", "my"),
    ):
        match = re.match(pattern, text)
        if match:
            parts = [int(p) for p in match.groups()]
            try:
                if order == "ymd":
                    return date(parts[0], parts[1], parts[2])
                if order == "dmy":
                    return date(parts[2], parts[1], parts[0])
                if order == "ym":
                    return date(parts[0], parts[1], 1)
                return date(parts[1], parts[0], 1)
            except ValueError:
                return None
    if re.fullmatch(r"(19|20)\d{2}", text):
        return date(int(text), 1, 1)
    for name, number in _MONTHS.items():
        if text.startswith(name):
            year = re.search(r"(19|20)\d{2}", text)
            return date(int(year.group(0)), number, 1) if year else date(2000, number, 1)
    return None


def _from_lines(name: str, lines: list[list[str]]) -> Table:
    lines = [row for row in lines if any(cell.strip() for cell in row)]
    if len(lines) < 2:
        raise TableError("The sheet has no data rows under a header row.")
    width = max(len(row) for row in lines)
    header = [
        (lines[0][i].strip() if i < len(lines[0]) else "") or f"Ustun {i + 1}" for i in range(width)
    ]
    body = [[(row[i].strip() if i < len(row) else "") for i in range(width)] for row in lines[1:]]
    truncated = len(body) > MAX_ROWS
    return Table(name=name, columns=header, rows=body[:MAX_ROWS], truncated=truncated)


def parse_csv_bytes(data: bytes, name: str) -> Table:
    text = decode_text(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return _from_lines(name, [list(r) for r in csv.reader(io.StringIO(text), dialect)])


def parse_extracted(
    text: str, sections: list[dict[str, Any]] | None, sheet_names: list[str]
) -> list[Table]:
    """Sheets from extracted workbook text ("a | b | c" rows)."""
    blocks: list[tuple[str, str]] = []
    if sections:
        for index, section in enumerate(sections):
            heading = str(section.get("heading") or "")
            label = heading.removeprefix("Sheet: ").strip() or f"Varaq {index + 1}"
            blocks.append((label, text[int(section["start"]) : int(section["end"])]))
    else:
        for index, block in enumerate(b for b in text.split("\n\n") if b.strip()):
            label = sheet_names[index] if index < len(sheet_names) else f"Varaq {index + 1}"
            blocks.append((label, block))
    tables = []
    for label, block in blocks:
        rows = [line.split(" | ") for line in block.splitlines() if line.strip()]
        try:
            tables.append(_from_lines(label, rows))
        except TableError:
            continue
    return tables


async def load_tables(db: AsyncSession, storage: Any, document: KnowledgeDocument) -> list[Table]:
    name = document.title or document.filename or "jadval"
    if document.mime_type in CSV_MIMES or (document.filename or "").lower().endswith(".csv"):
        if not document.storage_key:
            raise TableError("The file is not stored.")
        return [parse_csv_bytes(await storage.get(document.storage_key), name)]
    if document.current_revision_id is None or document.status not in (
        "indexed",
        "ready",
        "partial",
    ):
        raise TableError(
            "The workbook has not been read yet (it is read safely by the document worker; "
            "with COMPOSE_PROFILES=documents)."
        )
    revision = await db.get(DocumentRevision, document.current_revision_id)
    if revision is None or not revision.raw_text.strip():
        raise TableError("No table text was extracted from this workbook.")
    sections = (revision.meta or {}).get("sections")
    names = [str(s) for s in (document.meta or {}).get("sheets") or []]
    tables = parse_extracted(
        revision.raw_text, sections if isinstance(sections, list) else None, names
    )
    if not tables:
        raise TableError("No table with a header row was found in this workbook.")
    return tables
