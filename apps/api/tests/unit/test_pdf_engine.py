"""The offline PDF engine on real PDF files (generated in the test)."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from pypdf import PdfReader

from ezo_api.documents.pdf import engine
from ezo_api.documents.pdf.engine import PdfError
from tests.pdf_fixtures import encrypted, make_pdf, signed_marker, texts_of

A = make_pdf(["Alpha one", "Alpha two", "Alpha three"], title="A")
B = make_pdf(["Beta one", "Beta two"])
C = make_pdf(["Gamma one"])


def test_merge_keeps_order_and_is_verified() -> None:
    result = engine.merge([A, B, C])
    assert result.pages == 6 and not result.warnings
    assert texts_of(result.data) == [
        "Alpha one",
        "Alpha two",
        "Alpha three",
        "Beta one",
        "Beta two",
        "Gamma one",
    ]
    assert engine.verify_pdf(result.data, 6) == 6
    with pytest.raises(PdfError, match="at least two"):
        engine.merge([A])


def test_merge_then_delete_the_last_page() -> None:
    merged = engine.merge([A, B])
    last_gone = engine.delete_pages(merged.data, engine.parse_pages("last", merged.pages))
    assert texts_of(last_gone.data) == ["Alpha one", "Alpha two", "Alpha three", "Beta one"]


def test_page_specs_are_one_based_and_validated() -> None:
    assert engine.parse_pages("1-3, 5", 6) == [1, 2, 3, 5]
    assert engine.parse_pages("4-", 6) == [4, 5, 6]
    assert engine.parse_pages("last", 6) == [6]
    assert engine.parse_pages("2, 2, 1", 6) == [2, 1]  # order kept, duplicates removed
    for bad in ("0", "7", "3-1", "x", "1-2-3", ""):
        with pytest.raises(PdfError):
            engine.parse_pages(bad, 6)


def test_select_reorder_move_and_split() -> None:
    assert texts_of(engine.select_pages(A, [3, 1]).data) == ["Alpha three", "Alpha one"]
    assert texts_of(engine.reorder(A, [2, 3, 1]).data) == ["Alpha two", "Alpha three", "Alpha one"]
    with pytest.raises(PdfError, match="every page"):
        engine.reorder(A, [1, 2])
    moved = engine.move_page(engine.merge([A, B, C]).data, 6, 1)
    assert texts_of(moved.data)[:2] == ["Gamma one", "Alpha one"] and moved.pages == 6
    parts = engine.split(A, [[1], [2, 3]])
    assert [p.pages for p in parts] == [1, 2] and texts_of(parts[1].data) == [
        "Alpha two",
        "Alpha three",
    ]
    assert [p.pages for p in engine.split_every(A, 2)] == [2, 1]


def test_delete_refuses_to_empty_a_document() -> None:
    with pytest.raises(PdfError, match="empty"):
        engine.delete_pages(C, [1])


def test_rotate_and_normalize_orientation() -> None:
    rotated = engine.rotate(A, [2], 90)
    pages = PdfReader(io.BytesIO(rotated.data)).pages
    assert [p.rotation for p in pages] == [0, 90, 0]
    with pytest.raises(PdfError):
        engine.rotate(A, None, 45)
    mixed = make_pdf(["portrait", "wide"], landscape_pages={2})
    normal = engine.normalize_orientation(mixed)
    assert [p.rotation for p in PdfReader(io.BytesIO(normal.data)).pages] == [0, 90]
    dims = [
        (float(p.mediabox.width), float(p.mediabox.height))
        for p in PdfReader(io.BytesIO(normal.data)).pages
    ]
    original = [
        (float(p.mediabox.width), float(p.mediabox.height))
        for p in PdfReader(io.BytesIO(mixed)).pages
    ]
    assert dims == original  # page sizes are preserved; only the display rotation changes


def test_page_numbers_watermark_and_header_footer_are_real_text() -> None:
    numbered = engine.add_page_numbers(A, template="{n} / {total}", position="bottom-right")
    assert [t.endswith(f"{n} / 3") for n, t in enumerate(texts_of(numbered.data), start=1)] == [
        True
    ] * 3
    marked = engine.add_watermark(A, "MAXFIY")
    assert all("MAXFIY" in t for t in texts_of(marked.data))
    framed = engine.add_header_footer(B, header="Hisobot 2026", footer="Sahifa {n} / {total}")
    assert (
        texts_of(framed.data)[1].startswith("Hisobot 2026")
        or "Hisobot 2026" in texts_of(framed.data)[1]
    )
    assert "Sahifa 2 / 2" in texts_of(framed.data)[1]
    with pytest.raises(PdfError):
        engine.add_page_numbers(A, template="no number")
    # rotated pages get an upright stamp as well
    turned = engine.add_page_numbers(engine.rotate(A, [1], 90).data)
    assert texts_of(turned.data)[0].endswith("1")


def test_compress_is_lossless_and_honest() -> None:
    result = engine.compress(A)
    assert texts_of(result.data) == texts_of(A) and result.pages == 3
    assert len(result.data) <= len(A)
    if len(result.data) == len(A):
        assert any("original size" in w for w in result.warnings)


def test_metadata_is_cleaned_only_on_request() -> None:
    info = engine.inspect_pdf(A)
    assert info.metadata.get("Title") == "A" and info.metadata.get("Author") == "EZO tests"
    merged = engine.merge([A, B])
    assert engine.inspect_pdf(merged.data).page_count == 5
    clean = engine.clean_metadata(A)
    assert "Title" not in engine.inspect_pdf(clean.data).metadata and texts_of(
        clean.data
    ) == texts_of(A)


def test_inspect_detects_text_layer_and_scans() -> None:
    info = engine.inspect_pdf(A)
    assert info.text_layer == "full" and info.scanned_pages == [] and info.page_count == 3
    image = Image.new("RGB", (600, 800), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    scan = engine.images_to_pdf([buffer.getvalue(), buffer.getvalue()])
    assert scan.pages == 2
    assert engine.inspect_pdf(scan.data).text_layer == "none"
    mixed = engine.merge([A, scan.data])
    assert engine.inspect_pdf(mixed.data).scanned_pages == [4, 5]


def test_render_pages_to_images() -> None:
    images = engine.render_pages(A, [1, 3], dpi=72)
    assert len(images) == 2
    first = Image.open(io.BytesIO(images[0]))
    assert first.format == "PNG" and abs(first.width - 595) <= 2  # A4 at 72 dpi


def test_compare_pdfs_reports_changed_pages_and_metadata() -> None:
    other = make_pdf(["Alpha one", "Alpha TWO changed", "Alpha three"], title="B")
    comparison = engine.compare_pdfs(A, other)
    assert comparison.changed_pages == [2] and comparison.pages_a == comparison.pages_b == 3
    assert "Title" in comparison.metadata_changes
    assert "pages with different text: 2" in comparison.summary()


def test_encrypted_restricted_and_corrupt_inputs_are_refused() -> None:
    with pytest.raises(PdfError, match="password-protected") as caught:
        engine.merge([encrypted(A), B])
    assert caught.value.code == "encrypted"
    # Opens without a user password, but its permissions forbid changes.
    locked = encrypted(A, user_password="", permissions=0)
    with pytest.raises(PdfError, match="permissions"):
        engine.delete_pages(locked, [1])
    assert engine.inspect_pdf(locked).page_count == 3  # reading is still allowed
    for bad, code in ((b"", "empty"), (b"hello", "not_pdf"), (A[:200], "corrupt")):
        with pytest.raises(PdfError) as error:
            engine.inspect_pdf(bad)
        assert error.value.code == code


def test_signed_pdfs_get_a_warning() -> None:
    signed = signed_marker(A)
    assert engine.inspect_pdf(signed).signed
    result = engine.delete_pages(signed, [1])
    assert any("signature" in w for w in result.warnings)
    assert not engine.delete_pages(A, [1]).warnings


def test_verification_catches_wrong_page_counts() -> None:
    with pytest.raises(PdfError, match="expected 4"):
        engine.verify_pdf(A, 4)
