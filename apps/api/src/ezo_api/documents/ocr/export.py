"""What OCR read, as files people can work with.

- **Editable Word**: paragraphs and headings in reading order, one page after another.
  Best for editing and copying text.
- **Layout Word**: every recognised line kept on its own line with its indentation,
  vertical spacing and approximate font size, on a page of the original's size. Closer
  to the look of the scan; not a pixel copy (fonts, columns and images are not rebuilt).
- **Searchable PDF**: the original page images with an invisible text layer written by
  Tesseract, so the PDF looks exactly like the scan but can be searched and copied.

Pages where nothing could be read get a visible placeholder ("[page 3: no text could be
read]") in the Word files; EZO never fills in text.
"""

from __future__ import annotations

import io
import statistics
from typing import Literal

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.shared import Emu, Inches, Pt, RGBColor
from pypdf import PdfReader, PdfWriter

from ezo_api.documents.ocr.model import OCRError, OCRLine, OCRPage, OCRResult
from ezo_api.documents.ocr.tesseract import TesseractOCRProvider

DocxMode = Literal["editable", "layout"]
DEFAULT_DPI = 300


def _paragraphs(lines: list[OCRLine]) -> list[tuple[str, list[OCRLine]]]:
    groups: list[tuple[tuple[int, int], list[OCRLine]]] = []
    for line in lines:
        key = (line.block, line.paragraph)
        if groups and groups[-1][0] == key:
            groups[-1][1].append(line)
        else:
            groups.append((key, [line]))
    result = []
    for _, members in groups:
        text = ""
        for line in members:
            if text.endswith("-") and line.text[:1].islower():
                text = text[:-1] + line.text  # re-join a word hyphenated at the line end
            else:
                text = f"{text} {line.text}".strip()
        result.append((text, members))
    return result


def _placeholder(document: object, number: int) -> None:
    paragraph = document.add_paragraph()  # type: ignore[attr-defined]
    run = paragraph.add_run(f"[page {number}: no text could be read]")
    run.italic = True
    run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)


def ocr_to_docx(result: OCRResult, *, mode: DocxMode = "editable", title: str = "") -> bytes:
    document = Document()
    document.core_properties.title = title[:200]
    document.core_properties.comments = (
        f"Text read by OCR ({result.engine_version}); check it against the original."
    )
    heights = [ln.bbox[3] for p in result.pages for ln in p.lines if ln.bbox[3] > 0]
    median = statistics.median(heights) if heights else 0
    for index, page in enumerate(result.pages):
        if mode == "layout":
            _layout_page(document, page, first=index == 0)
            continue
        if index:
            document.add_page_break()  # type: ignore[no-untyped-call]
        if not page.text.strip():
            _placeholder(document, page.number)
            continue
        for text, members in _paragraphs(page.lines):
            tallest = max(ln.bbox[3] for ln in members)
            if len(members) == 1 and median and tallest > 1.35 * median and len(text) < 120:
                document.add_heading(text, level=1 if tallest > 1.8 * median else 2)
            else:
                document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _layout_page(document: object, page: OCRPage, *, first: bool) -> None:
    dpi = page.dpi or DEFAULT_DPI
    section = (
        document.sections[0]  # type: ignore[attr-defined]
        if first
        else document.add_section(WD_SECTION.NEW_PAGE)  # type: ignore[attr-defined]
    )
    if page.width and page.height:
        section.page_width = Emu(int(page.width / dpi * 914400))
        section.page_height = Emu(int(page.height / dpi * 914400))
        section.orientation = (
            WD_ORIENT.LANDSCAPE if page.width > page.height else WD_ORIENT.PORTRAIT
        )
    margin = Inches(0.4)
    section.left_margin = section.right_margin = margin
    section.top_margin = section.bottom_margin = margin
    if not page.lines:
        _placeholder(document, page.number)
        return
    previous_bottom: float | None = None
    for line in page.lines:
        left, top, _, height = line.bbox
        paragraph = document.add_paragraph()  # type: ignore[attr-defined]
        fmt = paragraph.paragraph_format
        indent = left / dpi - margin.inches
        fmt.left_indent = Inches(max(0.0, indent))
        gap_pt = 0.0 if previous_bottom is None else max(0.0, (top - previous_bottom) / dpi * 72)
        if previous_bottom is None:
            gap_pt = max(0.0, top / dpi * 72 - margin.pt)
        fmt.space_before = Pt(min(gap_pt, 200))
        fmt.space_after = Pt(0)
        size = min(max(height / dpi * 72 * 0.8, 6), 32)
        fmt.line_spacing = Pt(size * 1.15)
        run = paragraph.add_run(line.text)
        run.font.size = Pt(round(size * 2) / 2)
        previous_bottom = top + height


def merge_pages(pages: list[bytes]) -> bytes:
    writer = PdfWriter()
    for page in pages:
        reader = PdfReader(io.BytesIO(page))
        for item in reader.pages:
            writer.add_page(item)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def check_searchable(data: bytes, expected_pages: int) -> int:
    """Reopen the generated PDF: page count must match and it must carry text."""
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) != expected_pages:
        raise OCRError(
            f"The searchable PDF has {len(reader.pages)} pages, expected {expected_pages}.",
            "verification_failed",
        )
    return sum(len((p.extract_text() or "").strip()) for p in reader.pages)


def searchable_pdf(
    provider: TesseractOCRProvider,
    data: bytes,
    mime_type: str,
    *,
    languages: list[str] | None = None,
) -> tuple[bytes, list[int], list[str]]:
    """(pdf, pages that got a text layer, warnings). Pages that already have text are
    copied unchanged; scanned pages (or an image) are replaced by Tesseract's
    image + invisible-text page. The result is reopened and verified."""
    from ezo_api.documents.pdf import engine
    from ezo_api.documents.pdf.engine import PdfError

    usable, warnings = provider.resolve_languages(languages)
    if mime_type != "application/pdf" and data[:5] != b"%PDF-":
        from ezo_api.visual.images import ImageRejectedError, open_image

        try:
            image = open_image(data)
        except ImageRejectedError as exc:
            raise OCRError(str(exc), "bad_image") from exc
        dpi_info = image.info.get("dpi")
        dpi = (
            round(float(dpi_info[0]))
            if isinstance(dpi_info, tuple) and dpi_info[0]
            else DEFAULT_DPI
        )
        pdf = provider.pdf_page(image, 1, usable, dpi)
        check_searchable(pdf, 1)
        return pdf, [1], warnings
    try:
        info = engine.inspect_pdf(data)
        reader = engine.open_pdf(data, for_change=False)
    except PdfError as exc:
        raise OCRError(exc.message, exc.code) from exc
    scanned = info.scanned_pages[: provider.max_pages]
    if len(info.scanned_pages) > provider.max_pages:
        warnings.append(
            f"Only the first {provider.max_pages} scanned pages got a text layer (server limit "
            "EZO_OCR_MAX_PAGES); the other pages are unchanged."
        )
    if not scanned:
        raise OCRError("Every page of this PDF already has a text layer.", "not_needed")
    writer = PdfWriter()
    for number, page in enumerate(reader.pages, start=1):
        if number not in scanned:
            writer.add_page(page)
            continue
        try:
            [png] = engine.render_pages(data, [number], dpi=provider.dpi)
        except PdfError as exc:
            raise OCRError(exc.message, exc.code) from exc
        from PIL import Image

        image = Image.open(io.BytesIO(png))
        image.load()
        page_pdf = PdfReader(io.BytesIO(provider.pdf_page(image, number, usable, provider.dpi)))
        writer.add_page(page_pdf.pages[0])
    buffer = io.BytesIO()
    writer.write(buffer)
    result = buffer.getvalue()
    check_searchable(result, info.page_count)
    return result, scanned, warnings
