"""DocumentSpec → PDF (reportlab), with embedded Unicode fonts so Uzbek (Latin and
Cyrillic) and Russian text render correctly on any device."""

from __future__ import annotations

import io
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)
from reportlab.platypus import Paragraph as PdfParagraph
from reportlab.platypus import (
    Table as PdfTable,
)

from ezo_api.documents import fonts
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

FONT, FONT_BOLD = "EzoSans", "EzoSans-Bold"
ACCENT = colors.HexColor("#0b7a72")
INK = colors.HexColor("#1f2733")
MUTED = colors.HexColor("#5b6675")
_registered = False


def register_fonts() -> None:
    global _registered
    if _registered:
        return
    pdfmetrics.registerFont(TTFont(FONT, str(fonts.REGULAR)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(fonts.BOLD)))
    pdfmetrics.registerFontFamily(
        FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD
    )
    _registered = True


def _markup(runs: tuple[Run, ...]) -> str:
    out = []
    for run in runs:
        text = escape(run.text)
        if run.code:
            text = f'<font face="Courier">{text}</font>'
        if run.bold:
            text = f"<b>{text}</b>"
        if run.italic:
            text = f"<i>{text}</i>"
        if run.link:
            text = f'<link href="{escape(run.link)}" color="#0b7a72">{text}</link>'
        out.append(text)
    return "".join(out)


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "body",
        fontName=FONT,
        fontSize=10.5,
        leading=15,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    return {
        "title": ParagraphStyle(
            "title",
            parent=base,
            fontName=FONT_BOLD,
            fontSize=22,
            leading=27,
            spaceAfter=4,
            textColor=INK,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base, fontSize=12, textColor=MUTED, spaceAfter=14
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base,
            fontName=FONT_BOLD,
            fontSize=16,
            leading=20,
            spaceBefore=12,
            spaceAfter=6,
            textColor=ACCENT,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base,
            fontName=FONT_BOLD,
            fontSize=13,
            leading=17,
            spaceBefore=10,
            spaceAfter=4,
            textColor=ACCENT,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base,
            fontName=FONT_BOLD,
            fontSize=11.5,
            leading=15,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "body": base,
        "quote": ParagraphStyle(
            "quote", parent=base, leftIndent=12, textColor=MUTED, borderPadding=6
        ),
        "cell": ParagraphStyle("cell", parent=base, fontSize=9.5, leading=12, spaceAfter=0),
        "cell_head": ParagraphStyle(
            "cell_head",
            parent=base,
            fontName=FONT_BOLD,
            fontSize=9.5,
            leading=12,
            spaceAfter=0,
            textColor=colors.white,
        ),
    }


def render_pdf(spec: DocumentSpec) -> bytes:
    register_fonts()
    styles = _styles()
    story: list = []  # type: ignore[type-arg]
    story.append(PdfParagraph(escape(spec.title), styles["title"]))
    if spec.subtitle:
        story.append(PdfParagraph(escape(spec.subtitle), styles["subtitle"]))
    else:
        story.append(Spacer(1, 8))
    width = A4[0] - 40 * mm

    for block in spec.blocks:
        if isinstance(block, Heading):
            story.append(PdfParagraph(_markup(block.runs), styles[f"h{min(block.level, 3)}"]))
        elif isinstance(block, Paragraph):
            story.append(PdfParagraph(_markup(block.runs), styles["body"]))
        elif isinstance(block, Quote):
            story.append(PdfParagraph(_markup(block.runs), styles["quote"]))
        elif isinstance(block, ListBlock):
            story.append(
                ListFlowable(
                    [
                        ListItem(PdfParagraph(_markup(item), styles["body"]), leftIndent=14)
                        for item in block.items
                    ],
                    bulletType="1" if block.ordered else "bullet",
                    bulletFontName=FONT,
                    bulletFontSize=9 if not block.ordered else 10,
                    leftIndent=14,
                )
            )
        elif isinstance(block, CodeBlock):
            story.append(
                Preformatted(
                    block.text, ParagraphStyle("code", fontName="Courier", fontSize=8.5, leading=11)
                )
            )
        elif isinstance(block, Table):
            data = [[PdfParagraph(escape(c), styles["cell_head"]) for c in block.header]]
            data += [[PdfParagraph(escape(c), styles["cell"]) for c in row] for row in block.rows]
            columns = max(len(block.header), 1)
            table = PdfTable(data, colWidths=[width / columns] * columns, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f2f5f7")],
                        ),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d1dc")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.extend([table, Spacer(1, 8)])
        elif isinstance(block, Rule):
            story.append(
                HRFlowable(
                    width="100%", color=colors.HexColor("#c9d1dc"), spaceBefore=6, spaceAfter=6
                )
            )

    buffer = io.BytesIO()

    def footer(canvas, document) -> None:  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"{document.page}")
        canvas.restoreState()

    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=spec.title,
        author=spec.author,
        lang=spec.language,
    )
    template.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
