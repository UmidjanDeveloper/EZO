"""Real OCR with the local Tesseract engine on generated page images (uz Latin, uz
Cyrillic, Russian, English), plus orientation, deskew, scanned PDFs and limits."""

from __future__ import annotations

import pytest

from ezo_api.documents.ocr import NoOCRProvider, OCRError, TesseractOCRProvider, build_ocr_provider
from ezo_api.documents.ocr.preprocess import estimate_skew
from ezo_api.documents.ocr.tesseract import lines_to_text, parse_tsv
from ezo_api.documents.pdf import engine
from tests.ocr_fixtures import (
    ENGLISH,
    REQUIRED,
    RUSSIAN,
    UZ_CYRILLIC,
    UZ_LATIN,
    needs_tesseract,
    page_image,
    png,
    recall,
)

TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "1\t1\t0\t0\t0\t0\t0\t0\t800\t400\t-1\t\n"
    "4\t1\t1\t1\t1\t0\t10\t10\t300\t30\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t10\t10\t100\t30\t96.5\tSalom\n"
    "5\t1\t1\t1\t1\t2\t120\t10\t100\t30\t80.0\tdunyo\n"
    "4\t1\t2\t1\t1\t0\t10\t80\t200\t30\t-1\t\n"
    "5\t1\t2\t1\t1\t1\t10\t80\t200\t30\t91.0\tIkkinchi\n"
)


def test_tsv_becomes_lines_with_boxes_and_confidence() -> None:
    lines = parse_tsv(TSV)
    assert [line.text for line in lines] == ["Salom dunyo", "Ikkinchi"]
    assert lines[0].bbox == (10, 10, 300, 30)
    assert lines[0].confidence == pytest.approx((5 * 96.5 + 5 * 80.0) / 10, abs=0.1)
    assert lines_to_text(lines) == "Salom dunyo\n\nIkkinchi"  # new block → new paragraph


async def test_without_an_engine_nothing_is_invented() -> None:
    provider = build_ocr_provider(
        "auto", "no-such-tesseract-binary", ["uzb"], timeout_seconds=10, max_pages=5
    )
    assert isinstance(provider, NoOCRProvider) and not provider.available
    assert "not installed" in provider.status()["reason"]
    with pytest.raises(OCRError) as caught:
        await provider.extract(b"x", "image/png")
    assert caught.value.code == "unavailable"
    off = build_ocr_provider("none", "tesseract", ["uzb"], timeout_seconds=10, max_pages=5)
    assert "turned off" in off.status()["reason"]


def test_deskew_estimate() -> None:
    assert abs(estimate_skew(page_image(ENGLISH, skew=3)) - (-3.0)) <= 0.5
    assert abs(estimate_skew(page_image(ENGLISH))) <= 0.25


@pytest.fixture(scope="module")
def tesseract() -> TesseractOCRProvider:
    provider = TesseractOCRProvider.discover("tesseract", ["uzb", "uzb_cyrl", "rus", "eng"])
    if provider is None:
        if REQUIRED:
            pytest.fail("EZO_REQUIRE_TESSERACT is set but Tesseract with the packs is missing")
        pytest.skip("Tesseract with the uzb/uzb_cyrl/rus/eng packs is not installed")
    return provider


@needs_tesseract
@pytest.mark.parametrize(
    ("lines", "script", "first_pack", "language"),
    [
        (UZ_LATIN, "Latin", "uzb", "uz"),
        (UZ_CYRILLIC, "Cyrillic", "uzb_cyrl", "uz"),
        (RUSSIAN, "Cyrillic", "uzb_cyrl", "ru"),
        (ENGLISH, "Latin", "uzb", "en"),
    ],
)
def test_real_ocr_in_four_languages(
    tesseract: TesseractOCRProvider,
    lines: list[str],
    script: str,
    first_pack: str,
    language: str,
) -> None:
    result = tesseract.extract_sync(png(page_image(lines)), "image/png")
    [page] = result.pages
    assert recall(lines, page.text) >= 0.9, page.text
    assert page.script == script and page.languages.split("+")[0] == first_pack
    assert page.detected_language == language
    assert page.confidence is not None and page.confidence >= 80
    assert page.lines and all(line.bbox[2] > 0 for line in page.lines)
    assert len(page.source_sha256) == 64 and result.engine == "tesseract"


@needs_tesseract
def test_sideways_and_skewed_scans_are_straightened(tesseract: TesseractOCRProvider) -> None:
    sideways = tesseract.extract_sync(png(page_image(RUSSIAN, rotate=90)), "image/png").pages[0]
    assert sideways.rotation == 90 and recall(RUSSIAN, sideways.text) >= 0.9
    skewed = tesseract.extract_sync(png(page_image(UZ_LATIN, skew=3)), "image/png").pages[0]
    assert abs(skewed.deskew_angle + 3) <= 0.5 and recall(UZ_LATIN, skewed.text) >= 0.9


@needs_tesseract
def test_scanned_pdf_pages_keep_their_page_numbers(tesseract: TesseractOCRProvider) -> None:
    scan = engine.images_to_pdf([png(page_image(ENGLISH)), png(page_image(UZ_LATIN))]).data
    result = tesseract.extract_sync(scan, "application/pdf", pages=[2])
    [page] = result.pages
    assert page.number == 2 and recall(UZ_LATIN, page.text) >= 0.9 and page.dpi


@needs_tesseract
def test_page_limit_is_reported_not_hidden(tesseract: TesseractOCRProvider) -> None:
    limited = TesseractOCRProvider(
        tesseract.binary, tesseract.version, tesseract.installed, ["eng"], max_pages=1
    )
    scan = engine.images_to_pdf([png(page_image(ENGLISH))] * 2).data
    result = limited.extract_sync(scan, "application/pdf")
    assert [p.number for p in result.pages] == [1]
    assert any("were not read" in w for w in result.warnings)


@needs_tesseract
def test_blank_and_unreadable_images_get_no_invented_text(
    tesseract: TesseractOCRProvider,
) -> None:
    blank = tesseract.extract_sync(png(page_image([])), "image/png").pages[0]
    assert blank.text == "" and blank.confidence is None
    assert any("No text was recognised" in w for w in blank.warnings)


@needs_tesseract
def test_language_packs_are_checked_not_invented(tesseract: TesseractOCRProvider) -> None:
    assert tesseract.resolve_languages(None)[0] == ["uzb", "uzb_cyrl", "rus", "eng"]
    usable, warnings = tesseract.resolve_languages(["rus", "zzz"])
    assert usable == ["rus"] and "“zzz” is not installed" in warnings[0]
    with pytest.raises(OCRError) as caught:
        tesseract.resolve_languages(["zzz", "uzb; rm -rf /"])
    assert caught.value.code == "missing_language"
    result = tesseract.extract_sync(png(page_image(RUSSIAN)), "image/png", languages=["rus"])
    assert result.pages[0].languages == "rus"
    assert tesseract.status()["languages"]["uzb_cyrl"] == "Uzbek (Cyrillic)"
