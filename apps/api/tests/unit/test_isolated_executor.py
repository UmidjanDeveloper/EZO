"""Protocol and hostile EPUB preflight regressions, without native execution."""

import io
import subprocess
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


@pytest.mark.parametrize(
    "operation,message,code",
    [
        (
            "create",
            'Conflict. The container name "/ezo-native-active-v1" is already in use '
            'by container "fixture"',
            "executor_busy",
        ),
        (
            "create",
            'Conflict. The container name "/other" is already in use',
            "executor_unavailable",
        ),
        ("create", "Cannot connect to the Docker daemon", "executor_unavailable"),
        (
            "start",
            'Conflict. The container name "/ezo-native-active-v1" is already in use',
            "executor_unavailable",
        ),
    ],
)
def test_only_reserved_create_conflict_is_backpressure(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    message: str,
    code: str,
) -> None:
    def failed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            ["fixture-docker"], 1, stdout=b"", stderr=message.encode()
        )

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(ExecutorError, match=code):
        IsolatedExecutor._docker(operation)


def test_epub_spine_order_titles_and_multi_chapter_provenance() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml", '<container><rootfile full-path="OPS/book.opf"/></container>'
        )
        archive.writestr(
            "OPS/book.opf",
            "<package><manifest>"
            '<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="b" href="b.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="b"/><itemref idref="a"/></spine></package>',
        )
        archive.writestr(
            "OPS/a.xhtml", "<html><body><h1>Ўзбек 🙂</h1><p>Second in spine.</p></body></html>"
        )
        archive.writestr(
            "OPS/b.xhtml", "<html><body><h1>Birinchi bob</h1><p>First in spine.</p></body></html>"
        )
    result = parse_epub(output.getvalue())
    assert result.metadata["section_sources"] == ["OPS/b.xhtml", "OPS/a.xhtml"]
    assert [s.heading for s in result.sections] == ["Birinchi bob", "Ўзбек 🙂"]
    assert "First in spine." in result.sections[0].text


def test_extraction_rejects_database_incompatible_nuls_before_publication() -> None:
    with pytest.raises(ValidationError):
        ExtractionResult(source_sha256="0" * 64, text="x\x00y", sections=[])
    for field in ("heading", "member"):
        with pytest.raises(ValidationError):
            SourceSection.model_validate({"start": 0, "end": 1, field: "x\x00y"})
