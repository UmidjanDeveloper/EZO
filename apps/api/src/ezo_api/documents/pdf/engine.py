"""Offline PDF engine: inspect, merge, split, select, delete, reorder, rotate, number,
watermark, header/footer, compress, metadata, images ↔ PDF, compare, verify.

Rules:
- Input bytes are untrusted: header and size checks, a page limit, no password bypass.
  An encrypted PDF opens only when it needs no password, and only if its permissions
  allow assembling/modifying it.
- Page numbers given by users are 1-based; ranges are validated before anything runs.
- Every operation returns new bytes; the input is never changed. A result is reopened
  and its page count checked before it counts as a success (`verify_pdf`).
- Operations that change a digitally signed PDF return a warning: the signature will
  no longer be valid.
- No model, no network: everything here works without API keys.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.constants import UserAccessPermissions
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas as pdf_canvas

from ezo_api.documents.compare import Comparison, compare_texts
from ezo_api.documents.pdf.writer import FONT, register_fonts

MAX_INPUT_BYTES = 200 * 1024 * 1024
MAX_PAGES = 3_000
MAX_RENDER_PIXELS = 40_000_000
TEXT_PAGE_CHARS = 25
"""An image page with fewer extractable characters than this is treated as a scan."""

Position = Literal[
    "bottom-center", "bottom-right", "bottom-left", "top-center", "top-right", "top-left"
]


class PdfError(Exception):
    """A PDF problem; `message` is safe to show."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(slots=True)
class PdfResult:
    data: bytes
    pages: int
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PageInfo:
    number: int
    width: float
    height: float
    rotation: int
    text_chars: int
    images: int

    @property
    def needs_ocr(self) -> bool:
        """No text layer, or almost none on a page that carries an image (a scan)."""
        return self.text_chars == 0 or (self.text_chars < TEXT_PAGE_CHARS and self.images > 0)


@dataclass(frozen=True, slots=True)
class PdfInfo:
    pages: list[PageInfo]
    encrypted: bool
    signed: bool
    has_forms: bool
    metadata: dict[str, str]
    size: int

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def scanned_pages(self) -> list[int]:
        return [p.number for p in self.pages if p.needs_ocr]

    @property
    def text_layer(self) -> Literal["full", "partial", "none"]:
        scanned = len(self.scanned_pages)
        return "none" if scanned == len(self.pages) else "partial" if scanned else "full"


# --- opening and validation ----------------------------------------------------------------


def open_pdf(data: bytes, *, for_change: bool = True) -> PdfReader:
    if not data:
        raise PdfError("empty", "The PDF file is empty.")
    if len(data) > MAX_INPUT_BYTES:
        raise PdfError("too_large", "The PDF file is too large.")
    if b"%PDF-" not in data[:1024]:
        raise PdfError("not_pdf", "The file is not a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            if not reader.decrypt(""):
                raise PdfError(
                    "encrypted",
                    "The PDF is password-protected. EZO does not bypass passwords; open it with "
                    "its password and save an unprotected copy if you are allowed to.",
                )
            if for_change:
                permissions = reader.user_access_permissions or UserAccessPermissions(0)
                if not permissions & (
                    UserAccessPermissions.ASSEMBLE_DOC | UserAccessPermissions.MODIFY
                ):
                    raise PdfError(
                        "restricted",
                        "The PDF's permissions do not allow changing or assembling it.",
                    )
        count = len(reader.pages)
    except PdfError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError, RecursionError) as exc:
        raise PdfError("corrupt", "The PDF is damaged or not readable.") from exc
    if count == 0:
        raise PdfError("empty", "The PDF has no pages.")
    if count > MAX_PAGES:
        raise PdfError("too_many_pages", f"The PDF has more than {MAX_PAGES} pages.")
    return reader


def is_signed(reader: PdfReader) -> bool:
    try:
        root: Any = reader.trailer["/Root"]
        acro = root.get("/AcroForm")
        if acro is None:
            return False
        acro = acro.get_object()
        if int(acro.get("/SigFlags", 0)) & 1:
            return True
        for ref in acro.get("/Fields", []) or []:
            fld = ref.get_object()
            if fld.get("/FT") == "/Sig" and fld.get("/V") is not None:
                return True
    except (KeyError, AttributeError, TypeError, ValueError):
        return False
    return False


def _metadata(reader: PdfReader) -> dict[str, str]:
    raw: dict[str, Any] = dict(reader.metadata or {})
    return {str(k).lstrip("/"): str(v)[:500] for k, v in raw.items() if v is not None}


def inspect_pdf(data: bytes) -> PdfInfo:
    reader = open_pdf(data, for_change=False)
    pages: list[PageInfo] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # a broken content stream counts as "no text"
            text = ""
        try:
            images = len(page.images)
        except Exception:
            images = 0
        box = page.mediabox
        pages.append(
            PageInfo(
                number=number,
                width=float(box.width),
                height=float(box.height),
                rotation=int(page.rotation or 0) % 360,
                text_chars=len("".join(text.split())),
                images=images,
            )
        )
    root: Any = reader.trailer["/Root"]
    has_forms = "/AcroForm" in root
    return PdfInfo(
        pages, reader.is_encrypted, is_signed(reader), has_forms, _metadata(reader), len(data)
    )


def verify_pdf(data: bytes, expected_pages: int | None = None) -> int:
    """Reopen a generated PDF; its structure and page count must be right."""
    reader = open_pdf(data, for_change=False)
    count = len(reader.pages)
    if expected_pages is not None and count != expected_pages:
        raise PdfError(
            "verification_failed",
            f"The result has {count} pages, expected {expected_pages}.",
        )
    for page in reader.pages:  # every page object must be readable
        _ = page.mediabox
    return count


# --- page specifications ---------------------------------------------------------------------

_RANGE = re.compile(r"^(\d+|last)?\s*(?:[-–]\s*(\d+|last)?)?$")


def parse_pages(spec: str | Iterable[int], total: int) -> list[int]:
    """1-based pages from "1-3, 5, 8-", "last" or a list. Order is kept; duplicates removed."""
    if isinstance(spec, str):
        items: list[int] = []
        for part in [p.strip().lower() for p in spec.replace(";", ",").split(",") if p.strip()]:
            match = _RANGE.match(part)
            if not match or (match.group(1) is None and match.group(2) is None):
                raise PdfError("bad_pages", f"“{part}” is not a page or page range.")
            start_raw, end_raw = match.group(1), match.group(2)
            start = total if start_raw == "last" else int(start_raw) if start_raw else 1
            if "-" in part or "–" in part:
                end = total if end_raw in (None, "last") else int(end_raw)
            else:
                end = start
            if start > end:
                raise PdfError("bad_pages", f"The range “{part}” runs backwards.")
            items.extend(range(start, end + 1))
    else:
        items = [int(p) for p in spec]
    result: list[int] = []
    for page in items:
        if page < 1 or page > total:
            raise PdfError(
                "bad_pages", f"Page {page} does not exist (the document has {total} pages)."
            )
        if page not in result:
            result.append(page)
    if not result:
        raise PdfError("bad_pages", "No pages were selected.")
    return result


# --- writing helpers -------------------------------------------------------------------------


def _write(writer: PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def signature_warning(readers: Iterable[PdfReader]) -> list[str]:
    if any(is_signed(r) for r in readers):
        return [
            "A source PDF is digitally signed; the result is a new file and the original "
            "signature is not valid for it."
        ]
    return []


def _finish(writer: PdfWriter, readers: list[PdfReader], expected: int) -> PdfResult:
    data = _write(writer)
    verify_pdf(data, expected)
    return PdfResult(data, expected, signature_warning(readers))


# --- operations ------------------------------------------------------------------------------


def merge(files: list[bytes]) -> PdfResult:
    if len(files) < 2:
        raise PdfError("bad_input", "Merging needs at least two PDF files.")
    readers = [open_pdf(f) for f in files]
    writer = PdfWriter()
    total = 0
    for reader in readers:
        for page in reader.pages:
            writer.add_page(page)
            total += 1
    if total > MAX_PAGES:
        raise PdfError("too_many_pages", f"The merged PDF would have more than {MAX_PAGES} pages.")
    return _finish(writer, readers, total)


def select_pages(data: bytes, pages: list[int]) -> PdfResult:
    """A new PDF with exactly these pages in this order (extract, reorder)."""
    reader = open_pdf(data)
    chosen = parse_pages(pages, len(reader.pages))
    writer = PdfWriter()
    for number in chosen:
        writer.add_page(reader.pages[number - 1])
    return _finish(writer, [reader], len(chosen))


def delete_pages(data: bytes, pages: list[int]) -> PdfResult:
    reader = open_pdf(data)
    total = len(reader.pages)
    removed = set(parse_pages(pages, total))
    if len(removed) >= total:
        raise PdfError("bad_pages", "Deleting every page would leave an empty PDF.")
    return select_pages(data, [n for n in range(1, total + 1) if n not in removed])


def reorder(data: bytes, order: list[int]) -> PdfResult:
    reader = open_pdf(data)
    total = len(reader.pages)
    chosen = parse_pages(order, total)
    if sorted(chosen) != list(range(1, total + 1)):
        raise PdfError("bad_pages", f"A new order must list every page 1–{total} exactly once.")
    return select_pages(data, chosen)


def move_page(data: bytes, page: int, to_position: int) -> PdfResult:
    total = len(open_pdf(data).pages)
    parse_pages([page, to_position], total)
    order = [n for n in range(1, total + 1) if n != page]
    order.insert(to_position - 1, page)
    return reorder(data, order)


def split(data: bytes, ranges: list[list[int]]) -> list[PdfResult]:
    if not ranges:
        raise PdfError("bad_pages", "Name at least one page range to split into.")
    return [select_pages(data, part) for part in ranges]


def split_every(data: bytes, size: int = 1) -> list[PdfResult]:
    total = len(open_pdf(data).pages)
    if size < 1:
        raise PdfError("bad_pages", "Each part needs at least one page.")
    return split(
        data, [list(range(s, min(s + size, total + 1))) for s in range(1, total + 1, size)]
    )


def rotate(data: bytes, pages: list[int] | None, degrees: int) -> PdfResult:
    if degrees % 90 != 0:
        raise PdfError("bad_input", "Pages can be rotated by 90, 180 or 270 degrees.")
    reader = open_pdf(data)
    total = len(reader.pages)
    chosen = set(parse_pages(pages, total)) if pages else set(range(1, total + 1))
    writer = PdfWriter()
    for number, page in enumerate(reader.pages, start=1):
        added = writer.add_page(page)
        if number in chosen:
            added.rotate(degrees % 360)
    return _finish(writer, [reader], total)


def normalize_orientation(
    data: bytes, target: Literal["portrait", "landscape"] = "portrait"
) -> PdfResult:
    """Rotate pages that are displayed in the other orientation by 90°."""
    reader = open_pdf(data)
    turn: list[int] = []
    for number, page in enumerate(reader.pages, start=1):
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        if int(page.rotation or 0) % 180:
            width, height = height, width
        landscape = width > height
        if (target == "portrait" and landscape) or (target == "landscape" and not landscape):
            turn.append(number)
    if not turn:
        writer = PdfWriter(clone_from=reader)
        return _finish(writer, [reader], len(reader.pages))
    return rotate(data, turn, 90)


def _overlay(width: float, height: float, draw: Any) -> PdfReader:
    register_fonts()
    buffer = io.BytesIO()
    canvas = pdf_canvas.Canvas(buffer, pagesize=(width, height))
    draw(canvas, width, height)
    canvas.showPage()
    canvas.save()
    return PdfReader(io.BytesIO(buffer.getvalue()))


def _stamp(data: bytes, draw_for_page: Any, pages: list[int] | None = None) -> PdfResult:
    reader = open_pdf(data)
    total = len(reader.pages)
    chosen = set(parse_pages(pages, total)) if pages else set(range(1, total + 1))
    writer = PdfWriter()
    for number, page in enumerate(reader.pages, start=1):
        added = writer.add_page(page)
        if number not in chosen:
            continue
        box = added.mediabox
        width, height = float(box.width), float(box.height)
        rotation = int(added.rotation or 0) % 360
        view_w, view_h = (height, width) if rotation in (90, 270) else (width, height)
        stamp = _overlay(
            view_w, view_h, lambda c, w, h, n=number: draw_for_page(c, w, h, n, total)
        ).pages[0]
        if rotation:
            # Draw upright as the reader sees the page, then map onto the rotated page.
            if rotation == 90:
                matrix = Transformation().rotate(90).translate(width, 0)
            elif rotation == 180:
                matrix = Transformation().rotate(180).translate(width, height)
            else:
                matrix = Transformation().rotate(270).translate(0, height)
            added.merge_transformed_page(stamp, matrix)
        else:
            added.merge_page(stamp)
        added[NameObject("/MediaBox")] = box
    return _finish(writer, [reader], total)


def add_page_numbers(
    data: bytes,
    *,
    position: Position = "bottom-center",
    start: int = 1,
    template: str = "{n}",
    size: float = 10,
) -> PdfResult:
    if "{n}" not in template:
        raise PdfError("bad_input", "The page-number format must contain {n}.")

    def draw(c: pdf_canvas.Canvas, w: float, h: float, number: int, total: int) -> None:
        label = template.format(n=number + start - 1, total=total + start - 1)[:60]
        c.setFont(FONT, size)
        c.setFillColor(Color(0.2, 0.2, 0.2))
        y = 24 if position.startswith("bottom") else h - 24 - size
        if position.endswith("center"):
            c.drawCentredString(w / 2, y, label)
        elif position.endswith("right"):
            c.drawRightString(w - 36, y, label)
        else:
            c.drawString(36, y, label)

    return _stamp(data, draw)


def add_watermark(
    data: bytes, text: str, *, opacity: float = 0.15, pages: list[int] | None = None
) -> PdfResult:
    label = " ".join(text.split())[:80]
    if not label:
        raise PdfError("bad_input", "The watermark text is empty.")
    alpha = min(max(opacity, 0.05), 0.6)

    def draw(c: pdf_canvas.Canvas, w: float, h: float, number: int, total: int) -> None:
        size = max(18.0, min(w, h) / max(len(label), 6) * 1.6)
        c.saveState()
        c.setFillColor(Color(0.45, 0.45, 0.45, alpha=alpha))
        c.setFont(FONT, size)
        c.translate(w / 2, h / 2)
        c.rotate(45)
        c.drawCentredString(0, -size / 3, label)
        c.restoreState()

    return _stamp(data, draw, pages)


def add_header_footer(
    data: bytes, *, header: str = "", footer: str = "", size: float = 9
) -> PdfResult:
    header, footer = " ".join(header.split())[:150], " ".join(footer.split())[:150]
    if not header and not footer:
        raise PdfError("bad_input", "Give a header or a footer text.")

    def draw(c: pdf_canvas.Canvas, w: float, h: float, number: int, total: int) -> None:
        c.setFont(FONT, size)
        c.setFillColor(Color(0.25, 0.25, 0.25))
        values = {"n": number, "total": total}
        if header:
            c.drawCentredString(
                w / 2,
                h - 22 - size,
                header.replace("{n}", str(number)).replace("{total}", str(total)),
            )
        if footer:
            c.drawCentredString(w / 2, 14, footer.format_map(_Safe(values)))

    return _stamp(data, draw)


class _Safe(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def compress(data: bytes) -> PdfResult:
    """Lossless: compress content streams and drop duplicate/unused objects. Images untouched."""
    reader = open_pdf(data)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        page.compress_content_streams()
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    result = _finish(writer, [reader], len(reader.pages))
    if len(result.data) >= len(data):
        return PdfResult(
            data,
            result.pages,
            [
                *result.warnings,
                "The PDF could not be made smaller without losing quality; "
                "the original size is kept.",
            ],
        )
    return result


def clean_metadata(data: bytes) -> PdfResult:
    """Remove the document information dictionary and XMP metadata (only when asked)."""
    reader = open_pdf(data)
    writer = PdfWriter(clone_from=reader)
    writer.metadata = None
    root = writer._root_object  # pypdf has no public setter for removing XMP metadata
    if "/Metadata" in root:
        del root["/Metadata"]
    return _finish(writer, [reader], len(reader.pages))


def images_to_pdf(images: list[bytes]) -> PdfResult:
    from ezo_api.visual.images import ImageRejectedError, open_image  # local: optional heavy import

    if not images:
        raise PdfError("bad_input", "Give at least one image.")
    pages = []
    for raw in images:
        try:
            image = open_image(raw)
        except ImageRejectedError as exc:
            raise PdfError("bad_image", exc.message) from exc
        pages.append(image.convert("RGB"))
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    data = buffer.getvalue()
    verify_pdf(data, len(pages))
    return PdfResult(data, len(pages))


def render_pages(data: bytes, pages: list[int] | None = None, *, dpi: int = 150) -> list[bytes]:
    """PNG images of PDF pages (pypdfium2), with a pixel cap per page."""
    import pypdfium2 as pdfium

    open_pdf(data, for_change=False)  # validation and password rules first
    dpi = min(max(dpi, 36), 300)
    document = pdfium.PdfDocument(data)
    try:
        total = len(document)
        chosen = parse_pages(pages, total) if pages else list(range(1, total + 1))
        out: list[bytes] = []
        for number in chosen:
            page = document[number - 1]
            width, height = page.get_size()
            scale = dpi / 72
            if width * height * scale * scale > MAX_RENDER_PIXELS:
                scale = (MAX_RENDER_PIXELS / (width * height)) ** 0.5
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            out.append(buffer.getvalue())
            page.close()
        return out
    finally:
        document.close()


# --- comparison --------------------------------------------------------------------------


@dataclass(slots=True)
class PdfComparison:
    pages_a: int
    pages_b: int
    changed_pages: list[int]
    text: Comparison
    metadata_changes: dict[str, tuple[str | None, str | None]]

    def summary(self) -> str:
        parts = [f"{self.pages_a} vs {self.pages_b} pages", self.text.summary()]
        if self.changed_pages:
            shown = ", ".join(str(p) for p in self.changed_pages[:30])
            parts.append(f"pages with different text: {shown}")
        if self.metadata_changes:
            parts.append(f"metadata differs: {', '.join(sorted(self.metadata_changes))}")
        return "; ".join(parts)


def page_texts(data: bytes) -> list[str]:
    reader = open_pdf(data, for_change=False)
    texts = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            texts.append("")
    return texts


def compare_pdfs(a: bytes, b: bytes) -> PdfComparison:
    texts_a, texts_b = page_texts(a), page_texts(b)
    changed = [
        n
        for n in range(1, max(len(texts_a), len(texts_b)) + 1)
        if " ".join((texts_a[n - 1] if n <= len(texts_a) else "").split())
        != " ".join((texts_b[n - 1] if n <= len(texts_b) else "").split())
    ]
    meta_a = _metadata(open_pdf(a, for_change=False))
    meta_b = _metadata(open_pdf(b, for_change=False))
    meta = {
        k: (meta_a.get(k), meta_b.get(k))
        for k in set(meta_a) | set(meta_b)
        if meta_a.get(k) != meta_b.get(k)
    }
    return PdfComparison(
        len(texts_a),
        len(texts_b),
        changed,
        compare_texts("\n\n".join(texts_a), "\n\n".join(texts_b)),
        meta,
    )
