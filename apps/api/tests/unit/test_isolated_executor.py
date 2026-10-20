"""Protocol and hostile EPUB preflight regressions, without native execution."""

import io
import threading
import zipfile

import pytest
from pydantic import ValidationError

from ezo_api.documents.executor.controller import IsolatedExecutor
from ezo_api.documents.executor.epub import XML_BYTES, parse_epub, resolve
from ezo_api.documents.executor.protocol import (
    MAX_INPUT_BYTES,
    ExecutorError,
    ExtractionResult,
    SourceSection,
)
from ezo_api.knowledge.parsers.base import ParseError


def book(chapter: bytes = b"<html><body><p>Salom</p></body></html>") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>',
        )
        archive.writestr(
            "OPS/book.opf",
            '<package><manifest><item id="one" href="chapter.xhtml"'
            ' media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="one"/></spine></package>',
        )
        archive.writestr("OPS/chapter.xhtml", chapter)
    return output.getvalue()


def test_epub_unicode_provenance_and_inert_scripts() -> None:
    result = parse_epub(
        book(
            (
                "<html><body><p>Oʻzbek 🙂 Русский</p><script>secret script</script></body></html>"
            ).encode()
        )
    )
    assert result.text == "Oʻzbek 🙂 Русский"
    assert result.metadata["section_sources"] == ["OPS/chapter.xhtml"]


@pytest.mark.parametrize(
    "ref",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "https://example.com/a",
        "//example.com/a",
        "%252e%252e/secret",
        "..%5csecret",
    ],
)
def test_epub_rejects_unsafe_references(ref: str) -> None:
    with pytest.raises(ParseError):
        resolve("OPS/book.opf", ref)


def test_epub_rejects_small_compressed_expansion_before_xml_parse() -> None:
    data = book(b"<html><body>" + b"x" * XML_BYTES + b"</body></html>")
    assert len(data) < 10000
    with pytest.raises(ParseError, match="expanded-size"):
        parse_epub(data)


def test_epub_rejects_entities() -> None:
    with pytest.raises(ParseError):
        parse_epub(
            book(
                b'<!DOCTYPE html [<!ENTITY a SYSTEM "file:///etc/passwd">]><html><body>&a;</body></html>'
            )
        )


@pytest.mark.parametrize("start,end", [(0, 4), (2, 2), (0, 0)])
def test_result_requires_valid_exact_unicode_offsets(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        ExtractionResult(
            source_sha256="0" * 64, text="🙂Ўz", sections=[SourceSection(start=start, end=end)]
        )


def test_executor_rejects_mutable_image_selection() -> None:
    with pytest.raises(ValueError):
        IsolatedExecutor("ezo-executor:latest")


def test_oversized_input_fails_before_daemon_access() -> None:
    with pytest.raises(ExecutorError, match="input_limit"):
        IsolatedExecutor("sha256:" + "0" * 64).extract(b"x" * (MAX_INPUT_BYTES + 1), "pdf")


def test_cancelled_request_never_creates_workload() -> None:
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ExecutorError, match="cancelled"):
        IsolatedExecutor("sha256:" + "0" * 64).extract(b"x", "pdf", cancelled=cancelled)
