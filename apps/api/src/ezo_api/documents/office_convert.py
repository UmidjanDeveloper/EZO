"""DOCX / XLSX → PDF with LibreOffice (MPL-2.0), run as a separate, locked-down process.

Why LibreOffice: it lays out real Word and Excel files (styles, tables, headers, page
setup, sheets) far more faithfully than re-rendering their text. It is optional: when it
is not installed EZO says so and falls back to its own text-based PDF, labelled as such.

Safety:
- the binary comes from server configuration (`EZO_SOFFICE_CMD`), never from a request;
- fixed argument list, no shell, a fresh user profile and working directory per call
  (deleted afterwards), a minimal environment, a timeout that kills the whole process
  group, one conversion at a time per worker;
- files that link to external content (linked images, OLE links, external data) are
  refused, because opening them could make the server fetch URLs;
- input and output size limits; the PDF is reopened and its pages counted before it is
  returned.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from ezo_api.documents.isolation import native_fixtures_allowed
from ezo_api.documents.pdf import engine
from ezo_api.documents.pdf.engine import PdfError
from ezo_api.documents.process_limits import MAX_DIAGNOSTIC_BYTES, NativeOutputLimit, run_native

SourceKind = Literal["docx", "xlsx"]
MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = 200 * 1024 * 1024
MAX_PAGES = 1_000
_HYPERLINK = "relationships/hyperlink"
MAX_RELATIONSHIP_BYTES = 1024 * 1024
MAX_TOTAL_RELATIONSHIP_BYTES = 8 * 1024 * 1024


class OfficeConvertError(Exception):
    """Conversion failed. `message` is safe to show to the user."""

    def __init__(self, message: str, code: str = "convert_failed") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ConvertResult:
    pdf: bytes
    pages: int
    engine: str
    duration_ms: int


def external_links(data: bytes) -> list[str]:
    """Relationship types that point outside the file (other than plain hyperlinks)."""
    found: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = 0
            for info in archive.infolist():
                if not info.filename.endswith(".rels"):
                    continue
                total += info.file_size
                if info.file_size > MAX_RELATIONSHIP_BYTES or total > MAX_TOTAL_RELATIONSHIP_BYTES:
                    raise OfficeConvertError("Office relationship data is too large.", "too_large")
                root = fromstring(
                    archive.read(info), forbid_dtd=True, forbid_entities=True, forbid_external=True
                )
                for rel in root.iter():
                    if rel.tag.rsplit("}", 1)[-1] != "Relationship":
                        continue
                    if rel.get("TargetMode", "").casefold() != "external":
                        continue
                    relation_type = rel.get("Type", "")
                    if not relation_type.endswith(_HYPERLINK):
                        found.append(relation_type.rsplit("/", 1)[-1] or "external")
    except (DefusedXmlException, ParseError) as exc:
        raise OfficeConvertError(
            "The Office relationship XML is unsafe or damaged.", "corrupt"
        ) from exc
    except zipfile.BadZipFile as exc:
        raise OfficeConvertError("The file is damaged or not an Office file.", "corrupt") from exc
    return found


class OfficeConverter:
    """LibreOffice headless conversion to PDF."""

    def __init__(self, binary: str, version: str, timeout_seconds: float = 120.0) -> None:
        self.binary = binary
        self.version = version
        self.timeout_seconds = timeout_seconds

    @classmethod
    def discover(
        cls, command: str = "soffice", timeout_seconds: float = 120.0
    ) -> OfficeConverter | None:
        if not native_fixtures_allowed():
            return None
        binary = shutil.which(command) or (
            shutil.which("libreoffice") if command == "soffice" else None
        )
        if binary is None:
            return None
        try:
            out = subprocess.run(  # noqa: S603 - fixed binary from server config
                [binary, "--version"],
                capture_output=True,
                timeout=30,
                check=False,
                env=_env(tempfile.gettempdir()),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        version = out.stdout.decode("utf-8", "replace").strip().splitlines()
        return cls(binary, version[0][:80] if version else "LibreOffice", timeout_seconds)

    def status(self) -> dict[str, Any]:
        return {"available": True, "engine": self.version}

    def to_pdf_sync(self, data: bytes, kind: SourceKind) -> ConvertResult:
        import time

        if not data:
            raise OfficeConvertError("The file is empty.", "empty")
        if len(data) > MAX_INPUT_BYTES:
            raise OfficeConvertError("The file is too large to convert.", "too_large")
        links = external_links(data)
        if links:
            raise OfficeConvertError(
                "The file links to external content ("
                + ", ".join(sorted(set(links))[:5])
                + "). EZO does not open such files because that could fetch data from the "
                "internet. Embed the content in the file and try again.",
                "external_links",
            )
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="ezo-office-") as tmp:
            work = Path(tmp)
            source = work / f"input.{kind}"
            source.write_bytes(data)
            args = [
                self.binary,
                "--headless",
                "--norestore",
                "--nolockcheck",
                "--nodefault",
                "--nologo",
                "--nofirststartwizard",
                f"-env:UserInstallation=file://{work / 'profile'}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(work / "out"),
                str(source),
            ]
            try:
                completed = run_native(
                    args,
                    timeout=self.timeout_seconds,
                    file_limit=MAX_OUTPUT_BYTES,
                    stdout_limit=MAX_DIAGNOSTIC_BYTES,
                    cwd=work,
                    env=_env(tmp),
                )
            except NativeOutputLimit as exc:
                raise OfficeConvertError(
                    "The converter output was unexpectedly large.", "output_limit"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise OfficeConvertError(
                    f"Converting took longer than {self.timeout_seconds:.0f} seconds and was "
                    "stopped.",
                    "timeout",
                ) from exc
            except OSError as exc:
                raise OfficeConvertError(
                    "The Office converter could not be started.", "unavailable"
                ) from exc
            output = work / "out" / "input.pdf"
            if completed.returncode != 0 or not output.exists():
                detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
                raise OfficeConvertError(
                    "LibreOffice could not convert the file"
                    + (f": {detail[-1][:160]}" if detail else "."),
                )
            if output.stat().st_size >= MAX_OUTPUT_BYTES:
                raise OfficeConvertError("The PDF would be too large.", "output_limit")
            pdf = output.read_bytes()
        try:
            pages = engine.inspect_pdf(pdf).page_count
        except PdfError as exc:
            raise OfficeConvertError("The converted PDF could not be opened.", "verify") from exc
        if pages < 1 or pages > MAX_PAGES:
            raise OfficeConvertError(f"The converted PDF has {pages} pages; refused.", "verify")
        return ConvertResult(pdf, pages, self.version, round((time.monotonic() - started) * 1000))

    async def to_pdf(self, data: bytes, kind: SourceKind) -> ConvertResult:
        return await asyncio.to_thread(self.to_pdf_sync, data, kind)


def _env(home: str) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": home,
        "LANG": "C.UTF-8",
        "SAL_USE_VCLPLUGIN": "svp",
        "MAX_CONCURRENCY": "2",  # LibreOffice's supported thread-pool limit
        "MALLOC_ARENA_MAX": "2",
    }


def build_office_converter(
    mode: str, command: str, timeout_seconds: float
) -> OfficeConverter | None:
    if mode == "none":
        return None
    return OfficeConverter.discover(command, timeout_seconds)
