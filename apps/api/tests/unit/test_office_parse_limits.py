"""Compressed size is not a budget for XML trees or sparse spreadsheet expansion."""

import io
import zipfile

import pytest

from ezo_api.knowledge.parsers import ParseError, parse


def packed(name: str, xml: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, xml)
    return stream.getvalue()


@pytest.mark.parametrize(
    "kind,member", [("docx", "word/document.xml"), ("xlsx", "xl/sharedStrings.xml")]
)
def test_compressed_xml_rejected_before_library_parse(monkeypatch, kind, member):
    from ezo_api.knowledge.parsers import office

    def forbidden(*args, **kwargs):
        pytest.fail("unsafe archive reached the materializing library")

    monkeypatch.setattr(office.docx, "Document", forbidden)
    monkeypatch.setattr(office, "load_workbook", forbidden)
    data = packed(member, b"<root>" + b" " * (9 * 1024 * 1024) + b"</root>")
    assert len(data) < 12000
    with pytest.raises(ParseError, match="XML"):
        parse(kind, data, "a." + kind)


def test_many_docx_paragraphs_rejected_before_library_parse(monkeypatch):
    from ezo_api.knowledge.parsers import office

    def forbidden(*args, **kwargs):
        pytest.fail("complex tree reached python-docx")

    monkeypatch.setattr(office.docx, "Document", forbidden)
    data = packed("word/document.xml", b"<root>" + b"<p/>" * 20001 + b"</root>")
    with pytest.raises(ParseError, match="complex"):
        parse("docx", data, "a.docx")


@pytest.mark.parametrize(
    "xml",
    [
        b'<root><dimension ref="A1:XFD1048576"/></root>',
        b"<root>" + b"<x>" * 65 + b"</x>" * 65 + b"</root>",
        b'<!DOCTYPE r [<!ENTITY x "x">]><r>&x;</r>',
    ],
)
def test_sparse_dimensions_depth_and_entities_rejected(monkeypatch, xml):
    from ezo_api.knowledge.parsers import office

    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe XML reached openpyxl")

    monkeypatch.setattr(office, "load_workbook", forbidden)
    with pytest.raises(ParseError):
        parse("xlsx", packed("xl/worksheets/sheet1.xml", xml), "a.xlsx")


def test_docx_table_span_expansion_rejected_before_library_parse():
    data = packed(
        "word/document.xml", b'<root xmlns:w="word"><w:gridSpan w:val="2147483647"/></root>'
    )
    with pytest.raises(ParseError) as error:
        parse("docx", data, "a.docx")
    assert error.value.code == "too_complex"


def test_total_xml_budget_rejected(monkeypatch):
    from ezo_api.documents import ooxml_limits

    monkeypatch.setattr(ooxml_limits, "MAX_TOTAL_XML_BYTES", 30)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("a.xml", b"<root>1234567890</root>")
        archive.writestr("b.xml", b"<root>1234567890</root>")
    with pytest.raises(ParseError) as error:
        parse("docx", stream.getvalue(), "a.docx")
    assert error.value.code == "too_large"
