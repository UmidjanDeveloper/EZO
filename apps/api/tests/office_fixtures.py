"""Realistic Office files for export regression tests (generated, no third-party content)."""

from __future__ import annotations

import io

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from openpyxl import Workbook


def official_letter_docx() -> bytes:
    """Two-page official letter: letterhead header, PAGE footer, Latin + Cyrillic text,
    a numbered list, a table and a forced page break."""
    doc = Document()
    doc.styles["Normal"].font.name = "Times New Roman"
    doc.styles["Normal"].font.size = Pt(14)
    section = doc.sections[0]
    section.header.paragraphs[0].text = "XATIRCHI TUMANI HOKIMLIGI"
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "1"
    run.append(text)
    field.append(run)
    footer._p.append(field)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bold = title.add_run("XIZMAT XATI")
    bold.bold = True
    doc.add_paragraph("Navoiy viloyati hokimligiga")
    doc.add_paragraph(
        "Tumanda 2026-yil davomida 12 ta yangi maktab qurildi va 3 450 o'quvchi o'rni yaratildi."
    )
    doc.add_paragraph("Ўзбекистон Республикаси таълим тизимини ривожлантириш тўғрисида.")
    doc.add_paragraph("Maktablar ta'mirlandi.", style="List Number")
    doc.add_paragraph("O'qituvchilar malakasi oshirildi.", style="List Number")
    table = doc.add_table(rows=3, cols=3)
    table.style = "Table Grid"
    for r, row in enumerate(
        [("Mahalla", "Maktab", "O'rin"), ("Yangiobod", "4", "1200"), ("Bog'ishamol", "8", "2250")]
    ):
        for c, value in enumerate(row):
            table.cell(r, c).text = value
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    doc.add_paragraph("Ilova: 2 varaqda.")
    doc.add_paragraph("Hokim o'rinbosari ______________ [F.I.Sh.]")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def landscape_docx() -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    doc.add_paragraph("Keng jadval uchun albom varag'i.")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def report_xlsx() -> bytes:
    """Two sheets (Latin and Cyrillic), a SUM formula without a saved result."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Aholi"
    sheet.append(["Tuman", "Aholi"])
    sheet.append(["Xatirchi", 215000])
    sheet.append(["Navbahor", 130000])
    sheet.append(["Jami", "=SUM(B2:B3)"])
    second = workbook.create_sheet("Таблица")
    second.append(["Район", "Школы"])
    second.append(["Хатырчи", 64])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def with_external_image(docx: bytes) -> bytes:
    """The same Word file plus a relationship to an image on the internet."""
    import zipfile

    source = zipfile.ZipFile(io.BytesIO(docx))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/_rels/document.xml.rels":
                data = data.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rIdX" Type="http://schemas.openxmlformats.org/'
                    b'officeDocument/2006/relationships/image" Target="http://169.254.169.254/x.png"'
                    b' TargetMode="External"/></Relationships>',
                )
            target.writestr(item, data)
    return out.getvalue()
