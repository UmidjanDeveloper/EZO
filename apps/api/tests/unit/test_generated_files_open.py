"""Files EZO generates (chat and REST share these renderers) open in a real Office suite.

Each artifact is opened by LibreOffice (headless) and rendered to PDF; the rendered pages
must contain the content EZO put in. This is viewer evidence, not just "bytes exist".
"""

from __future__ import annotations

import io
import os
import shutil

import pytest
from pypdf import PdfReader

from ezo_api.documents.office_convert import OfficeConverter
from ezo_api.documents.render.build import build_deck
from ezo_api.documents.render.spec import DeckSpec, SlideSpec
from ezo_api.documents.spreadsheet.writer import Sheet, render_xlsx
from ezo_api.tools.document_tools import render_document

pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None and not os.environ.get("EZO_REQUIRE_OFFICE"),
    reason="LibreOffice is not installed",
)


def _rendered_text(data: bytes, kind: str) -> tuple[int, str]:
    converter = OfficeConverter.discover(timeout_seconds=120)
    assert converter is not None, "LibreOffice must be available when this test runs"
    result = converter.to_pdf_sync(data, kind)  # type: ignore[arg-type]
    reader = PdfReader(io.BytesIO(result.pdf))
    return len(reader.pages), " ".join(page.extract_text() for page in reader.pages)


def test_generated_docx_opens_with_its_content() -> None:
    markdown = (
        "# Oylik hisobot\n\nSotuv **12 %** o'sdi.\n\n"
        "| Oy | Summa |\n|---|---|\n| Oktyabr | 4 500 000 |"
    )
    docx = render_document(markdown, "Oylik hisobot", "docx", None)["docx"]
    pages, text = _rendered_text(docx, "docx")
    assert pages >= 1
    assert "Oylik hisobot" in text and "Oktyabr" in text and "4 500 000" in text


def test_generated_xlsx_opens_with_its_cells() -> None:
    xlsx = render_xlsx(
        [Sheet("Xarajatlar", ["Modda", "Summa"], [["Ijara", 4500000], ["Kommunal", 350000]])],
        "Xarajatlar",
    )
    pages, text = _rendered_text(xlsx, "xlsx")
    assert pages >= 1
    assert (
        "Ijara" in text
        and "Kommunal" in text
        and "4500000" in text.replace(" ", "").replace(",", "")
    )


def test_generated_pptx_opens_with_its_slides() -> None:
    deck = DeckSpec(
        title="Fotosintez",
        language="uz",
        slides=[
            SlideSpec(layout="title", title="Fotosintez", subtitle="Biologiya darsi"),
            SlideSpec(
                layout="bullets",
                title="Asosiy jarayon",
                bullets=["Yorug'lik energiyasi", "Suv va CO2"],
            ),
        ],
    )
    pptx = build_deck(deck, previews=False).pptx
    pages, text = _rendered_text(pptx, "pptx")
    assert pages == 2
    assert "Fotosintez" in text and "Asosiy jarayon" in text
