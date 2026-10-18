# ruff: noqa: E501  (multilingual phrase patterns are kept on one line each)
"""Natural-language PDF requests → ordered, validated steps (uz / en / ru, no model).

"Shu 4 ta PDFni birlashtir va oxirgi betini olib tashla" becomes
``[merge, delete(pages="last")]``. Steps keep the order in which the user said them.
Page numbers stay 1-based and symbolic ("last") until the engine resolves them
against the real document. When nothing is recognised the caller may ask a model
for the same structure (`PdfStep` validates either way).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ezo_api.core.text import normalize

PdfOp = Literal[
    "merge",
    "delete",
    "extract",
    "split",
    "rotate",
    "move",
    "page_numbers",
    "watermark",
    "header_footer",
    "compress",
    "clean_metadata",
    "to_images",
    "from_images",
    "normalize_orientation",
    "inspect",
]
CHANGING_OPS = frozenset(set(PdfOp.__args__) - {"inspect"})  # type: ignore[attr-defined]


class PdfStep(BaseModel):
    op: PdfOp
    pages: str | None = Field(default=None, max_length=200)
    """1-based pages/ranges: "2", "1-3,5", "last", "4-"."""
    to: int | None = Field(default=None, ge=1, le=100_000)
    degrees: int | None = None
    every: int | None = Field(default=None, ge=1, le=1_000)
    text: str | None = Field(default=None, max_length=150)
    header: str | None = Field(default=None, max_length=150)
    footer: str | None = Field(default=None, max_length=150)
    position: str | None = None

    @field_validator("pages")
    @classmethod
    def _pages(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower().replace(" ", "")
        if not re.fullmatch(r"(\d+|last)?(-(\d+|last)?)?(,(\d+|last)?(-(\d+|last)?)?)*", cleaned):
            raise ValueError("pages must look like 2, 1-3, 5, last or 4-")
        return cleaned

    @field_validator("degrees")
    @classmethod
    def _degrees(cls, value: int | None) -> int | None:
        if value is not None and value % 90 != 0:
            raise ValueError("degrees must be a multiple of 90")
        return value

    @model_validator(mode="after")
    def _required(self) -> PdfStep:
        if self.op in ("delete", "extract") and not self.pages:
            raise ValueError(f"{self.op} needs pages")
        if self.op == "move" and (not self.pages or self.to is None):
            raise ValueError("move needs pages (the page) and to (the new position)")
        if self.op == "watermark" and not self.text:
            raise ValueError("watermark needs text")
        if self.op == "header_footer" and not (self.header or self.footer):
            raise ValueError("header_footer needs a header or a footer")
        return self


# --- recognition -----------------------------------------------------------------------------

_PAGE_WORD = r"(?:bet|sahifa|varaq|page|pages|стр\w*|бет\w*)"
_NUM = r"(\d{1,5})"
_ORDINAL_LAST = r"(?:oxirgi|so'nggi|last|последн\w*|охирги)"
_ORDINAL_FIRST = r"(?:birinchi|first|перв\w*|биринчи)"
_LIST = rf"{_NUM}(?:\s*[-–]\s*{_NUM})?(?:\s*(?:,|va|and|и)\s*{_NUM}(?:\s*[-–]\s*{_NUM})?)*"

_PAGES_BEFORE = re.compile(
    rf"(?:{_LIST}|{_ORDINAL_LAST}|{_ORDINAL_FIRST})\s*[-–]?\s*{_PAGE_WORD}\w*"
)
_PAGES_AFTER = re.compile(
    rf"{_PAGE_WORD}\w*\s*(?:№\s*)?(?:{_LIST}|{_ORDINAL_LAST}|{_ORDINAL_FIRST})"
)

_OPS: list[tuple[PdfOp, re.Pattern[str]]] = [
    (
        "merge",
        re.compile(
            r"\b(birlashtir|qo'shib bitta|bitta (fayl|pdf|hujjat)\w* (qil|qilib)|bitta qil|merge|combine|join|объедин|склей|соедин)"
        ),
    ),
    ("delete", re.compile(r"\b(o'chir|olib tashla|delete|remove|удали|убери|ўчир)")),
    ("move", re.compile(r"\b(ko'chir|joyiga qo'y|move|перемест|перенеси|перестав|кўчир)")),
    (
        "extract",
        re.compile(
            r"\b(ajratib ol|chiqarib (ol|ber)|alohida pdf|extract|извлеки|вырежи|сохрани только)"
        ),
    ),
    (
        "split",
        re.compile(
            r"\b(bo'lib (ber|chiq)|bo'l\b|ajrat\b|ajratib ber|har (?:bir|\d{1,4}) bet\w* alohida|split|раздели|разбей)"
        ),
    ),
    ("rotate", re.compile(r"\b(bur(ib|a|ing)?\b|burab|rotate|turn|поверн|разверн)")),
    (
        "page_numbers",
        re.compile(
            r"\b((bet|sahifa) raqam\w*|raqamla|page numbers?|number the pages|нумерац|номера страниц|пронумеруй)"
        ),
    ),
    ("watermark", re.compile(r"\b(suv belgi\w*|watermark|водян\w* знак)")),
    (
        "header_footer",
        re.compile(r"\b(kolontitul|header|footer|колонтитул|yuqori qism\w*|pastki qism\w*)"),
    ),
    (
        "compress",
        re.compile(
            r"\b(siq|hajmini (kamaytir|kichrayt)|kichraytir|compress|shrink|reduce (the )?size|сжа|уменьш\w* размер)"
        ),
    ),
    ("clean_metadata", re.compile(r"\b(meta ?ma'lumot\w*|metadata|метадан\w*)")),
    (
        "to_images",
        re.compile(r"\b(rasm(ga|lar)|surat(ga|lar)|png|jpe?g|images?\b|картинк|изображени)"),
    ),
    ("normalize_orientation", re.compile(r"\b(yo'nalish\w*|orientation|ориентац)")),
    (
        "inspect",
        re.compile(
            r"\b(nechta (bet|sahifa)|necha (bet|sahifa)|how many pages|сколько страниц|skanerlanganmi|is it scanned)"
        ),
    ),
]
_QUOTED = re.compile(r"[\"“«'‘]([^\"”»'’]{1,150})[\"”»'’]")
_DEGREES = re.compile(r"(90|180|270)\s*(?:daraja|°|degrees?|градус\w*)?")
_LEFT = re.compile(r"\b(chap|left|влево|против час)")
_UPSIDE = re.compile(r"\b(teskari|upside down|вверх ногами)")
_EVERY = re.compile(r"\b(?:har|every|кажд\w*)\s+(\d{1,4})?\s*(?:bet|sahifa|page|стр)")
_TO_POSITION = re.compile(
    rf"(?:{_ORDINAL_FIRST}\s*(?:bet|sahifa|o'rin|page|position|стр\w*)\w*|{_NUM}\s*[-–]?\s*(?:bet|sahifa|o'rin)\w*ga|to (?:page |position )?{_NUM}|на {_NUM}|в начало|boshiga|to the (?:front|start|beginning))"
)


def _pages_in(fragment: str) -> str | None:
    for pattern in (_PAGES_BEFORE, _PAGES_AFTER):
        match = pattern.search(fragment)
        if not match:
            continue
        text = match.group(0)
        if re.search(_ORDINAL_LAST, text):
            return "last"
        if re.search(_ORDINAL_FIRST, text):
            return "1"
        numbers = re.sub(r"\s*(va|and|и)\s*", ",", text)
        spec = ",".join(
            m.group(0).replace(" ", "").replace("–", "-")
            for m in re.finditer(r"\d{1,5}(?:\s*[-–]\s*\d{1,5})?", numbers)
        )
        if spec:
            return spec
    return None


def parse_pdf_request(text: str) -> list[PdfStep]:
    """Ordered steps the user asked for; [] when nothing PDF-specific was recognised.

    Each recognised verb gets the text between the previous verb and the next one as
    its window, so "4-betni o'chir, 6-betni birinchi betga ko'chir" gives page 4 to the
    deletion and page 6 to the move (Uzbek puts pages before the verb, English after).
    """
    norm = normalize(text)
    quoted = [m.group(1).strip() for m in _QUOTED.finditer(text)]
    found: list[tuple[int, int, PdfOp]] = []
    for op, pattern in _OPS:
        for match in pattern.finditer(norm):
            if not any(start <= match.start() < end for start, end, _ in found):
                found.append((match.start(), match.end(), op))
    found.sort()
    steps: list[PdfStep] = []
    for index, (_, _, op) in enumerate(found):
        window_start = found[index - 1][1] if index else 0
        window_end = found[index + 1][0] if index + 1 < len(found) else len(norm)
        try:
            step = _build(op, norm[window_start:window_end], quoted)
        except ValueError:
            continue
        if step is not None and step not in steps:
            steps.append(step)
    return steps


def _build(op: PdfOp, clause: str, quoted: list[str]) -> PdfStep | None:
    pages = _pages_in(clause)
    if op in ("delete", "extract"):
        return PdfStep(op=op, pages=pages) if pages else None
    if op == "move":
        if not pages:
            return None
        target = _TO_POSITION.search(clause)
        if not target:
            return None
        numbers = [g for g in target.groups() if g]
        to = int(numbers[0]) if numbers else 1
        page = pages.split(",")[0].split("-")[0]
        return PdfStep(op="move", pages=page, to=to)
    if op == "split":
        every = _EVERY.search(clause)
        if every:
            return PdfStep(op="split", every=int(every.group(1) or 1))
        return PdfStep(op="split", pages=pages) if pages else PdfStep(op="split", every=1)
    if op == "rotate":
        degrees_match = _DEGREES.search(clause)
        degrees = (
            int(degrees_match.group(1))
            if degrees_match
            else (180 if _UPSIDE.search(clause) else 90)
        )
        if _LEFT.search(clause):
            degrees = 360 - degrees
        return PdfStep(op="rotate", pages=pages, degrees=degrees)
    if op == "watermark":
        return PdfStep(op="watermark", text=quoted[0]) if quoted else None
    if op == "header_footer":
        if not quoted:
            return None
        footer_first = bool(re.search(r"\b(footer|pastki|нижн)", clause)) and not re.search(
            r"\b(header|yuqori|верх)", clause
        )
        if len(quoted) >= 2:
            return PdfStep(op="header_footer", header=quoted[0], footer=quoted[1])
        return (
            PdfStep(op="header_footer", footer=quoted[0])
            if footer_first
            else PdfStep(op="header_footer", header=quoted[0])
        )
    if op == "clean_metadata":
        return (
            PdfStep(op=op)
            if re.search(r"\b(tozala|o'chir|olib tashla|clean|remove|strip|удали|очист)", clause)
            else None
        )
    if op == "to_images":
        return PdfStep(op=op, pages=pages)
    return PdfStep(op=op)
