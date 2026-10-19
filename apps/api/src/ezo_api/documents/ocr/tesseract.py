"""Local OCR with the Tesseract engine (Apache-2.0).

Security: the binary comes from server configuration (`EZO_TESSERACT_CMD`, resolved
with `shutil.which`), never from user input. It is run with a fixed argument list (no
shell), image bytes on stdin, a minimal environment, a timeout and an output limit.
Language identifiers are checked against the packs Tesseract reports as installed; EZO
never invents one.

Per page: orientation/script detection (`--psm 0 -l osd`) → turn the page upright when
Tesseract is confident → grayscale, contrast, upscale, deskew → recognition with TSV
output (words, lines, boxes and the engine's word confidence).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PIL import Image

from ezo_api.core.language import detect_language
from ezo_api.documents.ocr.model import (
    LOW_CONFIDENCE,
    NoOCRProvider,
    OCRError,
    OCRLine,
    OCRPage,
    OCRProvider,
    OCRResult,
)
from ezo_api.documents.ocr.preprocess import prepare, rotate_clockwise
from ezo_api.documents.process_limits import NativeOutputLimit, run_native

KNOWN_LANGUAGES: dict[str, str] = {
    "uzb": "Uzbek (Latin)",
    "uzb_cyrl": "Uzbek (Cyrillic)",
    "rus": "Russian",
    "eng": "English",
}
"""Language packs EZO uses by default. Other installed packs may be configured too."""
LATIN = ("uzb", "eng")
CYRILLIC = ("uzb_cyrl", "rus")
_LANG_ID = re.compile(r"^[a-z]{3}(?:_[a-z]{3,4})?$")
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MIN_ORIENTATION_CONFIDENCE = 1.5
DEFAULT_DPI = 300


@dataclass(frozen=True, slots=True)
class Orientation:
    rotate: int
    orientation_confidence: float
    script: str | None
    script_confidence: float


class TesseractOCRProvider(OCRProvider):
    name = "tesseract"

    def __init__(
        self,
        binary: str,
        version: str,
        installed: list[str],
        languages: list[str],
        *,
        timeout_seconds: float = 60.0,
        max_pages: int = 100,
        dpi: int = DEFAULT_DPI,
    ) -> None:
        self.binary = binary
        self.version = version
        self.installed = installed
        self.languages = [lang for lang in languages if lang in installed]
        self.missing = [lang for lang in languages if lang not in installed]
        self.timeout_seconds = timeout_seconds
        self.max_pages = max_pages
        self.dpi = dpi

    # ----------------------------------------------------------------- discovery

    @classmethod
    def discover(
        cls,
        command: str = "tesseract",
        languages: list[str] | None = None,
        **options: Any,
    ) -> TesseractOCRProvider | None:
        """The provider when Tesseract is installed (with at least one usable language
        pack), otherwise None."""
        binary = shutil.which(command)
        if binary is None:
            return None
        try:
            version_out = _run([binary, "--version"], b"", 10).decode("utf-8", "replace")
            langs_out = _run([binary, "--list-langs"], b"", 10).decode("utf-8", "replace")
        except OCRError:
            return None
        version = version_out.splitlines()[0].strip() if version_out else "tesseract"
        installed = [
            line.strip()
            for line in langs_out.splitlines()[1:]
            if _LANG_ID.match(line.strip()) and line.strip() != "osd"
        ]
        if "osd" in langs_out.split():
            installed.append("osd")
        provider = cls(binary, version, installed, languages or list(KNOWN_LANGUAGES), **options)
        return provider if provider.languages else None

    @property
    def has_osd(self) -> bool:
        return "osd" in self.installed

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": True,
            "version": self.version,
            "languages": {lang: KNOWN_LANGUAGES.get(lang, lang) for lang in self.languages},
            "missing_languages": self.missing,
            "orientation_detection": self.has_osd,
            "max_pages": self.max_pages,
        }

    # ----------------------------------------------------------------- languages

    def resolve_languages(self, requested: list[str] | None) -> tuple[list[str], list[str]]:
        """(usable packs, warnings). Requested packs that are not installed are reported,
        never silently replaced; if none is usable that is an error."""
        if not requested:
            return list(self.languages), []
        wanted = [lang for lang in dict.fromkeys(requested) if _LANG_ID.match(lang)]
        usable = [lang for lang in wanted if lang in self.installed and lang != "osd"]
        missing = [lang for lang in wanted if lang not in usable]
        warnings = [
            f"The OCR language pack “{lang}” is not installed on this server." for lang in missing
        ]
        if not usable:
            raise OCRError(
                "None of the requested OCR languages is installed on this server: "
                + ", ".join(missing or requested),
                "missing_language",
            )
        return usable, warnings

    def _ordered(self, languages: list[str], script: str | None) -> str:
        first = LATIN if script == "Latin" else CYRILLIC if script == "Cyrillic" else ()
        ordered = [lang for lang in first if lang in languages] + [
            lang for lang in languages if lang not in first
        ]
        return "+".join(ordered)

    # ----------------------------------------------------------------- running

    def _osd(self, png: bytes) -> Orientation | None:
        if not self.has_osd:
            return None
        try:
            out = _run(
                [self.binary, "stdin", "stdout", "--psm", "0", "-l", "osd"],
                png,
                self.timeout_seconds,
            ).decode("utf-8", "replace")
        except OCRError:
            return None  # too little text to detect orientation: read the page as it is

        def value(key: str) -> str | None:
            match = re.search(rf"^{key}:\s*(.+)$", out, re.MULTILINE)
            return match.group(1).strip() if match else None

        try:
            return Orientation(
                rotate=int(value("Rotate") or 0) % 360,
                orientation_confidence=float(value("Orientation confidence") or 0),
                script=value("Script"),
                script_confidence=float(value("Script confidence") or 0),
            )
        except ValueError:
            return None

    def _recognize(self, png: bytes, languages: str, dpi: int) -> list[OCRLine]:
        out = _run(
            [
                self.binary,
                "stdin",
                "stdout",
                "-l",
                languages,
                "--psm",
                "3",
                "--dpi",
                str(dpi),
                "tsv",
            ],
            png,
            self.timeout_seconds,
        )
        return parse_tsv(out.decode("utf-8", "replace"))

    def pdf_page(self, image: Image.Image, number: int, languages: list[str], dpi: int) -> bytes:
        """One searchable PDF page: the (upright) page image with an invisible text layer,
        written by Tesseract itself."""
        orientation = self._osd(_png(image.convert("L")))
        script = orientation.script if orientation else None
        if (
            orientation is not None
            and orientation.rotate
            and orientation.orientation_confidence >= MIN_ORIENTATION_CONFIDENCE
        ):
            image = rotate_clockwise(image, orientation.rotate)
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=80)
        return _run(
            [
                self.binary,
                "stdin",
                "stdout",
                "-l",
                self._ordered(languages, script),
                "--psm",
                "3",
                "--dpi",
                str(dpi),
                "pdf",
            ],
            buffer.getvalue(),
            self.timeout_seconds,
        )

    def read_image(
        self,
        image: Image.Image,
        number: int,
        languages: list[str],
        *,
        dpi: int | None = None,
    ) -> OCRPage:
        warnings: list[str] = []
        rotation = 0
        script: str | None = None
        orientation = self._osd(_png(image.convert("L")))
        if orientation is not None:
            script = orientation.script
            if (
                orientation.rotate
                and orientation.orientation_confidence >= MIN_ORIENTATION_CONFIDENCE
            ):
                rotation = orientation.rotate
                image = rotate_clockwise(image, rotation)
        prepared = prepare(image)
        png = _png(prepared.image)
        effective_dpi = dpi or DEFAULT_DPI
        if prepared.image.width != image.width and dpi:
            effective_dpi = round(dpi * prepared.image.width / image.width)
        packs = self._ordered(languages, script)
        lines = self._recognize(png, packs, effective_dpi)
        text = lines_to_text(lines)
        confidence = mean_confidence(lines)
        if not text.strip():
            warnings.append(f"No text was recognised on page {number}.")
        elif confidence is not None and confidence < LOW_CONFIDENCE:
            warnings.append(
                f"Page {number}: low recognition confidence (Tesseract mean {confidence:.0f}/100); "
                "check the text against the original."
            )
        return OCRPage(
            number=number,
            text=text,
            lines=lines,
            width=prepared.image.width,
            height=prepared.image.height,
            dpi=effective_dpi,
            languages=packs,
            script=script,
            detected_language=detect_language(text) if text.strip() else None,
            confidence=confidence,
            rotation=rotation,
            deskew_angle=prepared.deskew_angle,
            source_sha256=hashlib.sha256(png).hexdigest(),
            warnings=warnings,
        )

    def extract_sync(
        self,
        data: bytes,
        mime_type: str,
        *,
        languages: list[str] | None = None,
        pages: list[int] | None = None,
        on_page: Callable[[int, int], None] | None = None,
    ) -> OCRResult:
        started = time.monotonic()
        usable, warnings = self.resolve_languages(languages)
        results: list[OCRPage] = []
        if mime_type == "application/pdf" or data[:5] == b"%PDF-":
            from ezo_api.documents.pdf import engine
            from ezo_api.documents.pdf.engine import PdfError

            try:
                total = engine.inspect_pdf(data).page_count
            except PdfError as exc:
                raise OCRError(exc.message, exc.code) from exc
            wanted = [p for p in (pages or range(1, total + 1)) if 1 <= p <= total]
            if len(wanted) > self.max_pages:
                skipped = wanted[self.max_pages :]
                wanted = wanted[: self.max_pages]
                warnings.append(
                    f"OCR read the first {self.max_pages} of {len(wanted) + len(skipped)} pages "
                    f"(server limit EZO_OCR_MAX_PAGES); pages {skipped[0]}–{skipped[-1]} were "
                    "not read."
                )
            for index, number in enumerate(wanted, start=1):
                try:
                    [png] = engine.render_pages(data, [number], dpi=self.dpi)
                except PdfError as exc:
                    raise OCRError(exc.message, exc.code) from exc
                page_image: Image.Image = Image.open(io.BytesIO(png))
                page_image.load()
                results.append(self.read_image(page_image, number, usable, dpi=self.dpi))
                if on_page:
                    on_page(index, len(wanted))
        else:
            from ezo_api.visual.images import ImageRejectedError, open_image

            try:
                image = open_image(data)
            except ImageRejectedError as exc:
                raise OCRError(str(exc), "bad_image") from exc
            dpi = image.info.get("dpi")
            density = round(float(dpi[0])) if isinstance(dpi, tuple) and dpi and dpi[0] else None
            results.append(self.read_image(image, 1, usable, dpi=density))
            if on_page:
                on_page(1, 1)
        for page in results:
            warnings.extend(page.warnings)
        return OCRResult(
            pages=results,
            engine="tesseract",
            engine_version=self.version,
            warnings=warnings,
            duration_ms=round((time.monotonic() - started) * 1000),
        )

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        languages: list[str] | None = None,
        pages: list[int] | None = None,
    ) -> OCRResult:
        return await asyncio.to_thread(
            self.extract_sync, data, mime_type, languages=languages, pages=pages
        )


# --------------------------------------------------------------------------- helpers


def _run(args: list[str], stdin: bytes, timeout: float) -> bytes:
    """Run Tesseract: fixed argument list, no shell, minimal environment, bounded output."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "OMP_THREAD_LIMIT": "1"}
    if os.environ.get("TESSDATA_PREFIX"):
        env["TESSDATA_PREFIX"] = os.environ["TESSDATA_PREFIX"]
    try:
        completed = run_native(
            args,
            input=stdin,
            timeout=timeout,
            file_limit=MAX_OUTPUT_BYTES,
            stdout_limit=MAX_OUTPUT_BYTES,
            stderr_limit=MAX_OUTPUT_BYTES,
            env=env,
        )
    except NativeOutputLimit as exc:
        raise OCRError("The OCR output was unexpectedly large.", "output_limit") from exc
    except subprocess.TimeoutExpired as exc:
        raise OCRError(
            f"OCR took longer than {timeout:.0f} seconds and was stopped.", "timeout"
        ) from exc
    except OSError as exc:
        raise OCRError("The OCR engine could not be started.", "unavailable") from exc
    if len(completed.stdout) > MAX_OUTPUT_BYTES:
        raise OCRError("The OCR output was unexpectedly large.", "output_limit")
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OCRError(
            "The OCR engine failed" + (f": {detail[-1][:200]}" if detail else "."), "ocr_failed"
        )
    return completed.stdout


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def parse_tsv(tsv: str) -> list[OCRLine]:
    """Tesseract TSV → lines (words joined), with the line box and the mean word confidence."""
    lines: dict[tuple[int, int, int], dict[str, Any]] = {}
    for row in tsv.splitlines()[1:]:
        cells = row.split("\t")
        if len(cells) < 12:
            continue
        try:
            level, block, par, line = (int(cells[0]), int(cells[2]), int(cells[3]), int(cells[4]))
            left, top, width, height = (int(c) for c in cells[6:10])
            confidence = float(cells[10])
        except ValueError:
            continue
        key = (block, par, line)
        if level == 4:
            lines[key] = {"bbox": (left, top, width, height), "words": []}
        elif level == 5 and cells[11].strip():
            entry = lines.setdefault(key, {"bbox": (left, top, width, height), "words": []})
            entry["words"].append((cells[11].strip(), confidence, (left, top, width, height)))
    result: list[OCRLine] = []
    for (block, par, _), entry in lines.items():
        words = entry["words"]
        if not words:
            continue
        scored = [(w, c) for w, c, _ in words if c >= 0]
        weight = sum(len(w) for w, _ in scored)
        line_confidence = round(sum(len(w) * c for w, c in scored) / weight, 1) if weight else None
        result.append(
            OCRLine(
                " ".join(w for w, _, _ in words),
                entry["bbox"],
                line_confidence,
                block,
                par,
                tuple((w, box) for w, _, box in words),
            )
        )
    return result


def lines_to_text(lines: list[OCRLine]) -> str:
    parts: list[str] = []
    previous: tuple[int, int] | None = None
    for line in lines:
        paragraph = (line.block, line.paragraph)
        if previous is not None:
            parts.append("\n\n" if paragraph != previous else "\n")
        parts.append(line.text)
        previous = paragraph
    return "".join(parts).strip()


def mean_confidence(lines: list[OCRLine]) -> float | None:
    scored = [(len(line.text), line.confidence) for line in lines if line.confidence is not None]
    weight = sum(n for n, _ in scored)
    if not weight:
        return None
    return round(sum(n * (c or 0) for n, c in scored) / weight, 1)


def build_ocr_provider(
    mode: str,
    command: str,
    languages: list[str],
    *,
    timeout_seconds: float,
    max_pages: int,
) -> OCRProvider:
    if mode == "none":
        return NoOCRProvider("OCR is turned off (EZO_OCR_PROVIDER=none).")
    provider = TesseractOCRProvider.discover(
        command, languages, timeout_seconds=timeout_seconds, max_pages=max_pages
    )
    if provider is None:
        return NoOCRProvider(
            "Tesseract OCR is not installed on this server (or none of the configured language "
            "packs is). Install tesseract-ocr with the uzb, uzb-cyrl, rus and eng packs; see "
            "docs/OCR.md."
        )
    return provider
