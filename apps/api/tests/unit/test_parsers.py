import pytest

from ezo_api.knowledge.parsers import ParseError, parse
from tests.files import PNG_1PX, make_docx, make_pdf, make_xlsx


def test_pdf_pages_and_title() -> None:
    parsed = parse(
        "pdf", make_pdf(["First page text here", "Second page text"], "Annual report"), "a.pdf"
    )
    assert [s.page for s in parsed.sections] == [1, 2]
    assert "Second page text" in parsed.text
    assert parsed.title == "Annual report"
    assert parsed.metadata["pages"] == 2
    assert not parsed.needs_ocr


def test_pdf_without_text_needs_ocr() -> None:
    parsed = parse("pdf", make_pdf(["", ""]), "scan.pdf")
    assert parsed.needs_ocr


def test_broken_pdf_raises_readable_error() -> None:
    with pytest.raises(ParseError) as info:
        parse("pdf", b"%PDF-1.7\nthis is not really a pdf", "x.pdf")
    assert "PDF" in info.value.message


def test_docx_headings_paragraphs_and_tables() -> None:
    data = make_docx(
        "Shartnoma", ["Birinchi band.", "Ikkinchi band."], [["Nomi", "Narx"], ["Kitob", "50000"]]
    )
    parsed = parse("docx", data, "a.docx")
    assert parsed.title == "Shartnoma"
    assert "Kitob | 50000" in parsed.text
    assert parsed.sections[0].heading == "Shartnoma"


def test_xlsx_rows() -> None:
    parsed = parse(
        "xlsx", make_xlsx([["Oy", "Sotuv"], ["Yanvar", 120], ["Fevral", None]]), "a.xlsx"
    )
    assert "Yanvar | 120" in parsed.text
    assert parsed.metadata["sheets"] == ["Sales"]
    assert parsed.sections[0].heading == "Sheet: Sales"


def test_csv_semicolon_dialect() -> None:
    parsed = parse("csv", b"ism;ball\nAli;5\nVali;4\n", "a.csv")
    assert "Ali | 5" in parsed.text
    assert parsed.metadata["rows"] == 3


def test_markdown_sections() -> None:
    parsed = parse("markdown", b"# Qo'llanma\n\nKirish.\n\n## O'rnatish\n\nBuyruq.", "a.md")
    assert parsed.title == "Qo'llanma"
    assert [s.heading for s in parsed.sections] == ["Qo'llanma", "O'rnatish"]


def test_html_main_content() -> None:
    html = (
        "<html><head><title>EZO yangiliklari</title></head><body><nav>Menu Home About</nav>"
        "<article><h1>EZO yangiliklari</h1><p>"
        + "EZO yangi bilim bazasini ishga tushirdi va endi fayllarni o‘qiy oladi. " * 10
        + "</p></article><footer>Copyright</footer></body></html>"
    ).encode()
    parsed = parse("html", html, "page")
    assert "bilim bazasini" in parsed.text
    assert "Menu Home About" not in parsed.text


def test_image_needs_ocr() -> None:
    assert parse("image", PNG_1PX, "a.png").needs_ocr
