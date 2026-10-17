"""DocumentSpec → DOCX (python-docx). Uses real Word styles (Title, Heading 1–4,
List Bullet/Number, Quote, table grid) so the file stays editable and navigable."""

from __future__ import annotations

import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from ezo_api.documents.fonts import OFFICE_FONT
from ezo_api.documents.model import (
    CodeBlock,
    DocumentSpec,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Rule,
    Run,
    Table,
)

ACCENT = RGBColor(0x0B, 0x7A, 0x72)


def _add_runs(paragraph, runs: tuple[Run, ...]) -> None:  # type: ignore[no-untyped-def]
    for item in runs:
        run = paragraph.add_run(item.text)
        run.bold = item.bold or None
        run.italic = item.italic or None
        if item.code:
            run.font.name = "Consolas"
        if item.link:
            run.font.color.rgb = ACCENT
            run.underline = True


def render_docx(spec: DocumentSpec) -> bytes:
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = OFFICE_FONT
    normal.font.size = Pt(11)
    # East-Asian/complex fallbacks so Cyrillic and Uzbek use the same font.
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), OFFICE_FONT)
    for level in range(1, 5):
        style = document.styles[f"Heading {level}"]
        style.font.name = OFFICE_FONT
        style.font.color.rgb = ACCENT if level <= 2 else RGBColor(0x22, 0x2B, 0x38)

    document.core_properties.title = spec.title
    document.core_properties.author = spec.author
    document.core_properties.language = spec.language

    title = document.add_paragraph(spec.title, style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if spec.subtitle:
        document.add_paragraph(spec.subtitle, style="Subtitle")

    for block in spec.blocks:
        if isinstance(block, Heading):
            paragraph = document.add_heading(level=block.level)
            _add_runs(paragraph, block.runs)
        elif isinstance(block, Paragraph):
            _add_runs(document.add_paragraph(), block.runs)
        elif isinstance(block, ListBlock):
            style = "List Number" if block.ordered else "List Bullet"
            for item in block.items:
                _add_runs(document.add_paragraph(style=style), item)
        elif isinstance(block, Quote):
            _add_runs(document.add_paragraph(style="Intense Quote"), block.runs)
        elif isinstance(block, CodeBlock):
            paragraph = document.add_paragraph()
            run = paragraph.add_run(block.text)
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
        elif isinstance(block, Table):
            columns = max(len(block.header), 1)
            table = document.add_table(rows=1, cols=columns)
            table.style = "Light Grid Accent 1"
            for index, cell_text in enumerate(block.header):
                cell = table.rows[0].cells[index]
                cell.text = cell_text
                for run in cell.paragraphs[0].runs:
                    run.bold = True
            for row in block.rows:
                cells = table.add_row().cells
                for index in range(columns):
                    cells[index].text = row[index] if index < len(row) else ""
            document.add_paragraph()
        elif isinstance(block, Rule):
            document.add_paragraph("―" * 20).alignment = WD_ALIGN_PARAGRAPH.CENTER

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
