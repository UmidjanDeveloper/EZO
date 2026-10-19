"""DocumentSpec → DOCX (python-docx). Uses real Word styles (Title, Heading 1–4,
List Bullet/Number, Quote, table grid) so the file stays editable and navigable."""

from __future__ import annotations

import io
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

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
from ezo_api.organization.formatting import apply as apply_formatting
from ezo_api.organization.formatting import formatting_of
from ezo_api.organization.letterhead import Letterhead

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


def _letterhead(document: Any, letterhead: Letterhead) -> None:
    if letterhead.logo:
        picture = document.add_paragraph()
        picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
        picture.add_run().add_picture(io.BytesIO(letterhead.logo), height=Cm(2))
    for index, line in enumerate(letterhead.lines):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run(line).bold = index == 0
    if letterhead.contacts:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run(letterhead.contacts).font.size = Pt(9)
    rule = document.add_paragraph("―" * 30)
    rule.alignment = WD_ALIGN_PARAGRAPH.CENTER


def render_docx(spec: DocumentSpec, letterhead: Letterhead | None = None) -> bytes:
    """`letterhead`: the organization's logo, name lines and standard formatting."""
    document = Document()
    normal = document.styles["Normal"]
    if letterhead is not None:
        apply_formatting(document, formatting_of(letterhead.formatting))
    else:
        normal.font.name = OFFICE_FONT
        normal.font.size = Pt(11)
    # East-Asian/complex fallbacks so Cyrillic and Uzbek use the same font.
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), normal.font.name or OFFICE_FONT)
    for level in range(1, 5):
        style = document.styles[f"Heading {level}"]
        style.font.name = normal.font.name or OFFICE_FONT
        style.font.color.rgb = ACCENT if level <= 2 else RGBColor(0x22, 0x2B, 0x38)

    document.core_properties.title = spec.title
    document.core_properties.author = spec.author
    document.core_properties.language = spec.language

    if letterhead is not None:
        _letterhead(document, letterhead)
        document.core_properties.author = letterhead.name[:200]
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
