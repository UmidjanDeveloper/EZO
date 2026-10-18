"""Find tables in documents and turn them into spreadsheet sheets.

- **Word**: tables are read exactly from the file structure.
- **PDF with a text layer**: words and their positions come from PDFium; tables are
  *detected* from the layout (rows of aligned text blocks).
- **Scans and photos**: the same detection runs on the words OCR found.

Detection is a heuristic for ruled or clearly aligned tables. It does not understand
merged cells or tables without clear column gaps, and it says so: every detected table
carries warnings when rows have a different number of cells.
"""

from __future__ import annotations

import io
import statistics
from dataclasses import dataclass, field
from typing import Any

from ezo_api.documents.spreadsheet.writer import Sheet, coerce

Box = tuple[float, float, float, float]  # left, top, right, bottom (top < bottom)
MAX_TABLES = 50


@dataclass(slots=True)
class Word:
    text: str
    box: Box


@dataclass(slots=True)
class Table:
    rows: list[list[str]]
    source: str  # docx | pdf_text | ocr
    page: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def columns(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    def describe(self) -> str:
        where = f"page {self.page}" if self.page else "document"
        return f"{len(self.rows)} rows × {self.columns} columns ({where}, {self.source})"


# --------------------------------------------------------------------------- Word


def docx_tables(data: bytes) -> list[Table]:
    from docx import Document

    document = Document(io.BytesIO(data))
    tables: list[Table] = []
    for table in document.tables[:MAX_TABLES]:
        rows: list[list[str]] = []
        for row in table.rows:
            cells: list[str] = []
            previous = None
            for cell in row.cells:
                # A horizontally merged cell is returned once per grid column.
                cells.append("" if cell._tc is previous else cell.text.strip())
                previous = cell._tc
            rows.append(cells)
        if rows:
            tables.append(Table(rows, "docx"))
    return tables


# --------------------------------------------------------------------------- PDF text


def pdf_words(data: bytes, page_number: int) -> tuple[list[Word], float]:
    """Words on one page (PDFium character boxes joined at spaces and gaps) and the page
    height. Coordinates are flipped so that top < bottom like image coordinates."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[page_number - 1]
        height = page.get_height()
        text_page = page.get_textpage()
        words: list[Word] = []
        current = ""
        box: list[float] | None = None
        for index in range(text_page.count_chars()):
            char = text_page.get_text_range(index, 1)
            left, bottom, right, top = text_page.get_charbox(index, loose=True)
            gap = box is not None and left - box[2] > max((top - bottom) * 0.6, 1.5)
            if (
                not char.strip()
                or gap
                or (box is not None and abs(bottom - box[1]) > (top - bottom) * 0.8)
            ):
                if current.strip() and box is not None:
                    words.append(
                        Word(current.strip(), (box[0], height - box[3], box[2], height - box[1]))
                    )
                current, box = "", None
                if not char.strip():
                    continue
            current += char
            box = (
                [left, bottom, right, top]
                if box is None
                else [min(box[0], left), min(box[1], bottom), max(box[2], right), max(box[3], top)]
            )
        if current.strip() and box is not None:
            words.append(Word(current.strip(), (box[0], height - box[3], box[2], height - box[1])))
        text_page.close()
        page.close()
        return words, height
    finally:
        pdf.close()


def ocr_words(lines: list[dict[str, Any]]) -> list[Word]:
    """Words from stored OCR lines (`OCRLine.words`, boxes as left, top, width, height)."""
    words: list[Word] = []
    for line in lines:
        for text, (left, top, width, height) in line.get("words") or []:
            words.append(Word(str(text), (left, top, left + width, top + height)))
    return words


# --------------------------------------------------------------------------- detection


def _rows(words: list[Word]) -> list[list[Word]]:
    if not words:
        return []
    heights = [w.box[3] - w.box[1] for w in words if w.box[3] > w.box[1]]
    tolerance = (statistics.median(heights) if heights else 10) * 0.5
    ordered = sorted(words, key=lambda w: ((w.box[1] + w.box[3]) / 2, w.box[0]))
    rows: list[list[Word]] = []
    centre: float | None = None
    for word in ordered:
        middle = (word.box[1] + word.box[3]) / 2
        if centre is not None and abs(middle - centre) <= tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])
            centre = middle
    return [sorted(row, key=lambda w: w.box[0]) for row in rows]


def _cells(row: list[Word], gap: float) -> list[tuple[str, float, float]]:
    cells: list[tuple[str, float, float]] = []
    for word in row:
        if cells and word.box[0] - cells[-1][2] <= gap:
            text, left, _ = cells[-1]
            cells[-1] = (f"{text} {word.text}", left, word.box[2])
        else:
            cells.append((word.text, word.box[0], word.box[2]))
    return cells


def _columns(rows: list[list[tuple[str, float, float]]]) -> list[tuple[float, float]]:
    spans = sorted((left, right) for row in rows for _, left, right in row)
    merged: list[list[float]] = []
    for left, right in spans:
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    return [(a, b) for a, b in merged]


def detect_tables(words: list[Word], *, source: str, page: int | None) -> list[Table]:
    """Regions of at least 3 consecutive rows that split into ≥ 2 aligned columns."""
    rows = _rows(words)
    if not rows:
        return []
    heights = [w.box[3] - w.box[1] for w in words if w.box[3] > w.box[1]]
    unit = statistics.median(heights) if heights else 10
    gap = unit * 1.2
    cell_rows = [_cells(row, gap) for row in rows]
    tables: list[Table] = []
    start = 0
    while start < len(cell_rows):
        if len(cell_rows[start]) < 2:
            start += 1
            continue
        end = start
        while end + 1 < len(cell_rows) and len(cell_rows[end + 1]) >= 2:
            top_next = min(w.box[1] for w in rows[end + 1])
            bottom = max(w.box[3] for w in rows[end])
            if top_next - bottom > unit * 3:
                break
            end += 1
        region = cell_rows[start : end + 1]
        columns = _columns(region)
        if len(region) >= 3 and 2 <= len(columns) <= 30:
            table_rows: list[list[str]] = []
            uneven = 0
            for row in region:
                values = [""] * len(columns)
                for text, left, right in row:
                    overlaps = [min(right, b) - max(left, a) for a, b in columns]
                    target = overlaps.index(max(overlaps))
                    values[target] = f"{values[target]} {text}".strip()
                if len(row) != len(columns):
                    uneven += 1
                table_rows.append(values)
            table = Table(table_rows, source, page)
            if uneven:
                table.warnings.append(
                    f"{uneven} row(s) have fewer cells than columns (empty or merged cells); "
                    "check them against the original."
                )
            tables.append(table)
            if len(tables) >= MAX_TABLES:
                break
        start = end + 1
    return tables


# --------------------------------------------------------------------------- sheets


def to_sheets(tables: list[Table], base: str = "Table") -> list[Sheet]:
    sheets: list[Sheet] = []
    for number, table in enumerate(tables, start=1):
        rows = [list(r) + [""] * (table.columns - len(r)) for r in table.rows]
        header = rows[0]
        looks_like_header = all(isinstance(coerce(c), str) or not c for c in header) and any(
            c for c in header
        )
        if looks_like_header:
            columns = [c or f"Column {i + 1}" for i, c in enumerate(header)]
            body = rows[1:]
        else:
            columns = [f"Column {i + 1}" for i in range(table.columns)]
            body = rows
        name = f"{base} {number}" + (f" (p{table.page})" if table.page else "")
        sheets.append(Sheet(name, columns, body))
    return sheets
