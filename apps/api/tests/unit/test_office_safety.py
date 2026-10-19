"""Untrusted OOXML relationships must be inspected before LibreOffice is launched."""

import io
import zipfile

import pytest

from ezo_api.documents.office_convert import OfficeConvertError, external_links


def archive(xml: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as result:
        result.writestr("word/_rels/document.xml.rels", xml)
    return stream.getvalue()


@pytest.mark.parametrize("quote", ['"', "'"])
@pytest.mark.parametrize("prefix", ["", "r:"])
def test_external_relationships_cannot_hide_behind_xml_syntax(quote: str, prefix: str) -> None:
    xml = (
        "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships' "
        "xmlns:r='http://schemas.openxmlformats.org/package/2006/relationships'>"
        f"<{prefix}Relationship Id='rId1' Type='http://example.test/image' "
        f"TargetMode={quote}External{quote} Target='https://untrusted.test/image'/>"
        "</Relationships>"
    ).encode()
    assert external_links(archive(xml)) == ["image"]


def test_relationship_entities_are_rejected_without_reading_external_files() -> None:
    xml = b"""<!DOCTYPE Relationships [<!ENTITY secret SYSTEM "file:///etc/passwd">]>
    <Relationships><Relationship Type="image" Target="&secret;"/></Relationships>"""
    with pytest.raises(OfficeConvertError, match="relationship"):
        external_links(archive(xml))


def test_compressed_relationship_bomb_is_rejected_before_decompression() -> None:
    with pytest.raises(OfficeConvertError, match="relationship"):
        external_links(archive(b" " * (2 * 1024 * 1024)))
