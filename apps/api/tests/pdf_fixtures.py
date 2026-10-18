"""Real PDF files for tests, built with reportlab (no binary fixtures in the repository)."""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as pdf_canvas

from ezo_api.documents.pdf.writer import FONT, register_fonts


def make_pdf(
    texts: list[str], *, landscape_pages: set[int] | None = None, title: str = ""
) -> bytes:
    """One page per text (1-based `landscape_pages` are landscape). Unicode text supported."""
    register_fonts()
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    if title:
        c.setTitle(title)
        c.setAuthor("EZO tests")
    for number, text in enumerate(texts, start=1):
        size = landscape(A4) if number in (landscape_pages or set()) else A4
        c.setPageSize(size)
        c.setFont(FONT, 14)
        y = size[1] - 72
        for line in text.splitlines() or [""]:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()
    return buffer.getvalue()


def texts_of(data: bytes) -> list[str]:
    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(data)).pages]


def encrypted(
    data: bytes,
    user_password: str = "secret",  # noqa: S107 - throwaway test password
    owner_password: str = "owner",  # noqa: S107
    permissions: int = -1,
) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(
        user_password=user_password, owner_password=owner_password, permissions_flag=permissions
    )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def signed_marker(data: bytes) -> bytes:
    """A PDF whose AcroForm says it carries signatures (SigFlags), as signed PDFs do."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    acro = DictionaryObject(
        {
            NameObject("/SigFlags"): NumberObject(3),
            NameObject("/Fields"): writer._add_object(DictionaryObject()),
        }
    )
    writer._root_object[NameObject("/AcroForm")] = acro
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
