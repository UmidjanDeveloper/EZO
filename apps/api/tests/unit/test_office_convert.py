"""Word/Excel → PDF with LibreOffice: layout, scripts, formulas, limits and refusals."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from ezo_api.documents.docx import fidelity
from ezo_api.documents.office_convert import (
    OfficeConverter,
    OfficeConvertError,
    build_office_converter,
    external_links,
)
from tests.docx_fixtures import rich_docx
from tests.office import REQUIRE_OFFICE, requires_office
from tests.office_fixtures import (
    landscape_docx,
    official_letter_docx,
    report_xlsx,
    with_external_image,
)


@pytest.fixture(scope="module")
def converter() -> OfficeConverter:
    found = OfficeConverter.discover()
    if found is None:
        if REQUIRE_OFFICE:
            pytest.fail("EZO_REQUIRE_OFFICE is set but LibreOffice is missing")
        pytest.skip("LibreOffice is not installed")
    return found


def pages_text(pdf: bytes) -> list[str]:
    return [page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages]


@requires_office
def test_official_letter_keeps_pages_header_footer_table_and_scripts(
    converter: OfficeConverter,
) -> None:
    result = converter.to_pdf_sync(official_letter_docx(), "docx")
    assert result.pages == 2 and result.engine.startswith("LibreOffice")
    first, second = pages_text(result.pdf)
    assert "XATIRCHI TUMANI HOKIMLIGI" in first and "XATIRCHI TUMANI HOKIMLIGI" in second
    assert "XIZMAT XATI" in first and "3 450 o'quvchi" in first
    assert "Ўзбекистон Республикаси" in first  # Cyrillic survives
    assert "Bog'ishamol" in first and "2250" in first  # table cells
    assert first.rstrip().endswith("1") and second.rstrip().endswith("2")  # PAGE field
    assert "Ilova: 2 varaqda." in second  # the page break was honoured
    fonts = PdfReader(io.BytesIO(result.pdf)).pages[0]["/Resources"]["/Font"]
    assert len(fonts) >= 1


@requires_office
def test_page_orientation_and_edited_files(converter: OfficeConverter) -> None:
    wide = converter.to_pdf_sync(landscape_docx(), "docx")
    box = PdfReader(io.BytesIO(wide.pdf)).pages[0].mediabox
    assert float(box.width) > float(box.height)
    translated, _ = fidelity.apply_edits(rich_docx(), {0: "Lease agreement"})
    text = "".join(pages_text(converter.to_pdf_sync(translated, "docx").pdf))
    assert "Lease agreement" in text and "4 500 000 so'm" in text


@requires_office
def test_workbook_sheets_and_formulas(converter: OfficeConverter) -> None:
    result = converter.to_pdf_sync(report_xlsx(), "xlsx")
    first, second = pages_text(result.pdf)
    assert "Xatirchi 215000" in first and "Jami 345000" in first  # SUM computed by LibreOffice
    assert "Хатырчи 64" in second


@requires_office
def test_limits_and_refusals(converter: OfficeConverter) -> None:
    with pytest.raises(OfficeConvertError) as linked:
        converter.to_pdf_sync(with_external_image(official_letter_docx()), "docx")
    assert linked.value.code == "external_links" and "image" in linked.value.message
    for bad, code in ((b"", "empty"), (b"not a zip file", "corrupt")):
        with pytest.raises(OfficeConvertError) as caught:
            converter.to_pdf_sync(bad, "docx")
        assert caught.value.code == code
    slow = OfficeConverter(converter.binary, converter.version, timeout_seconds=0.05)
    with pytest.raises(OfficeConvertError) as timed_out:
        slow.to_pdf_sync(official_letter_docx(), "docx")
    assert timed_out.value.code == "timeout"
    # The converter still works after a killed run (no stale lock or profile).
    assert converter.to_pdf_sync(official_letter_docx(), "docx").pages == 2


def test_external_links_detection_and_switch_off() -> None:
    assert external_links(rich_docx()) == []  # an ordinary hyperlink is fine
    assert external_links(with_external_image(rich_docx())) == ["image"]
    assert build_office_converter("none", "soffice", 60) is None
    assert build_office_converter("auto", "no-such-office-binary", 60) is None
