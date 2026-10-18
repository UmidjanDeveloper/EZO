"""Run a list of PDF steps on input files, with page identity.

Page references in a request mean the pages as the user sees them in the input (for a
merge: in the merged document). "4-betni o'chir, 6-betni birinchi betga ko'chir"
therefore moves the original page 6 even though deleting page 4 shifted it.

Page-list steps (merge, delete, extract, move, rotate, orientation) only rearrange
references; the PDF is assembled once, then stamps (page numbers, watermark,
header/footer) and whole-file steps (compress, metadata) run on the result.
Split and to_images produce several outputs at the end. Every PDF output is
reopened and its page count verified (engine functions do this).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Literal

from pypdf import PdfReader, PdfWriter

from ezo_api.documents.pdf import engine
from ezo_api.documents.pdf.engine import PdfError
from ezo_api.documents.pdf.requests import PdfStep

MAX_OUTPUTS = 50


@dataclass(slots=True)
class PlanOutput:
    kind: Literal["pdf", "png"]
    data: bytes
    pages: int
    label: str


@dataclass(slots=True)
class PlanResult:
    outputs: list[PlanOutput]
    warnings: list[str] = field(default_factory=list)
    report: list[str] = field(default_factory=list)
    """Plain facts about what happened (for the reply and the artifact metadata)."""
    inspected: engine.PdfInfo | None = None


@dataclass(slots=True)
class _Page:
    source: int  # index into the input pages (after merging)
    rotate: int = 0


def _rotated(page_size: tuple[float, float], rotation: int) -> bool:
    width, height = page_size
    if rotation % 180:
        width, height = height, width
    return width > height


def run_plan(
    inputs: list[bytes], steps: list[PdfStep], *, images: list[bytes] | None = None
) -> PlanResult:
    if not steps:
        raise PdfError("bad_input", "No PDF operation was requested.")
    warnings: list[str] = []
    report: list[str] = []

    if steps[0].op == "from_images" or (images and not inputs):
        if not images:
            raise PdfError("bad_input", "Converting to PDF needs images.")
        built = engine.images_to_pdf(images)
        inputs = [built.data]
        report.append(f"{len(images)} image(s) were placed on {built.pages} PDF page(s).")
        steps = [s for s in steps if s.op != "from_images"]
        if not steps:
            return PlanResult(
                [PlanOutput("pdf", built.data, built.pages, "images")], warnings, report
            )
    if not inputs:
        raise PdfError("bad_input", "No PDF file was given.")

    if steps[0].op == "merge" or len(inputs) > 1:
        if len(inputs) < 2:
            raise PdfError("bad_input", "Merging needs at least two PDF files.")
        merged = engine.merge(inputs)
        warnings += merged.warnings
        source = merged.data
        report.append(
            f"{len(inputs)} PDF files were merged in the given order ({merged.pages} pages)."
        )
    else:
        source = inputs[0]
    steps = [s for s in steps if s.op != "merge"]

    if any(s.op == "inspect" for s in steps) and all(s.op == "inspect" for s in steps):
        info = engine.inspect_pdf(source)
        return PlanResult([], warnings, report, info)

    reader = engine.open_pdf(source)
    if engine.is_signed(reader) and not warnings:
        warnings += engine.signature_warning([reader])
    total = len(reader.pages)
    sizes = [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages]
    base_rotation = [int(p.rotation or 0) % 360 for p in reader.pages]
    current: list[_Page] = [_Page(i) for i in range(total)]

    def resolve(spec: str) -> list[int]:
        return [n - 1 for n in engine.parse_pages(spec, total)]

    def find(source_index: int) -> int:
        for position, page in enumerate(current):
            if page.source == source_index:
                return position
        raise PdfError(
            "bad_pages", f"Page {source_index + 1} was already removed by an earlier step."
        )

    stamps: list[PdfStep] = []
    finals: list[PdfStep] = []
    multi: PdfStep | None = None
    for step in steps:
        if step.op == "delete":
            gone = set(resolve(step.pages or ""))
            for index in gone:
                find(index)
            current = [p for p in current if p.source not in gone]
            if not current:
                raise PdfError("bad_pages", "Deleting these pages would leave an empty PDF.")
            report.append(f"Deleted page(s) {step.pages} (numbering of the input).")
        elif step.op == "extract":
            keep = resolve(step.pages or "")
            current = [current[find(i)] for i in keep]
            report.append(f"Kept only page(s) {step.pages}, in that order.")
        elif step.op == "move":
            index = resolve(step.pages or "")[0]
            page = current.pop(find(index))
            target = min(max((step.to or 1) - 1, 0), len(current))
            current.insert(target, page)
            report.append(f"Moved page {index + 1} to position {target + 1}.")
        elif step.op == "rotate":
            degrees = (step.degrees or 90) % 360
            chosen = set(resolve(step.pages)) if step.pages else {p.source for p in current}
            for page in current:
                if page.source in chosen:
                    page.rotate = (page.rotate + degrees) % 360
            report.append(
                f"Rotated {'page(s) ' + step.pages if step.pages else 'all pages'} by {degrees}°."
            )
        elif step.op == "normalize_orientation":
            turned = 0
            for page in current:
                if _rotated(sizes[page.source], base_rotation[page.source] + page.rotate):
                    page.rotate = (page.rotate + 90) % 360
                    turned += 1
            report.append(f"Turned {turned} landscape page(s) upright.")
        elif step.op in ("page_numbers", "watermark", "header_footer"):
            stamps.append(step)
        elif step.op in ("compress", "clean_metadata"):
            finals.append(step)
        elif step.op in ("split", "to_images"):
            multi = step
        elif step.op == "inspect":
            continue

    writer = PdfWriter()
    for page in current:
        added = writer.add_page(reader.pages[page.source])
        if page.rotate:
            added.rotate(page.rotate)
    buffer = io.BytesIO()
    writer.write(buffer)
    data = buffer.getvalue()
    engine.verify_pdf(data, len(current))

    for step in stamps:
        if step.op == "page_numbers":
            data = engine.add_page_numbers(data, template=step.text or "{n}").data
            report.append("Added page numbers.")
        elif step.op == "watermark":
            data = engine.add_watermark(data, step.text or "", pages=None).data
            report.append(f"Added the watermark “{step.text}”.")
        else:
            data = engine.add_header_footer(
                data, header=step.header or "", footer=step.footer or ""
            ).data
            report.append("Added the header/footer.")
    for step in finals:
        if step.op == "compress":
            before = len(data)
            result = engine.compress(data)
            data = result.data
            warnings += result.warnings
            report.append(f"Compressed losslessly: {before:,} → {len(data):,} bytes.")
        else:
            data = engine.clean_metadata(data).data
            report.append("Removed the document metadata (title, author, producer, XMP).")

    pages = engine.verify_pdf(data, len(current))
    if multi is None:
        return PlanResult([PlanOutput("pdf", data, pages, "result")], warnings, report)
    if multi.op == "split":
        parts = (
            engine.split_every(data, multi.every or 1)
            if multi.every or not multi.pages
            else engine.split(
                data, [engine.parse_pages(chunk, pages) for chunk in (multi.pages or "").split(",")]
            )
        )
        if len(parts) > MAX_OUTPUTS:
            raise PdfError(
                "too_many_outputs", f"Splitting would create more than {MAX_OUTPUTS} files."
            )
        report.append(f"Split into {len(parts)} file(s).")
        return PlanResult(
            [PlanOutput("pdf", p.data, p.pages, f"part-{i}") for i, p in enumerate(parts, start=1)],
            warnings,
            report,
        )
    rendered = engine.parse_pages(multi.pages, pages) if multi.pages else list(range(1, pages + 1))
    if len(rendered) > MAX_OUTPUTS:
        raise PdfError(
            "too_many_outputs", f"At most {MAX_OUTPUTS} pages can be turned into images at once."
        )
    images_out = engine.render_pages(data, rendered)
    report.append(f"Rendered {len(images_out)} page(s) as PNG images.")
    return PlanResult(
        [
            PlanOutput("png", img, 1, f"page-{n}")
            for n, img in zip(rendered, images_out, strict=True)
        ],
        warnings,
        report,
    )


def page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)
