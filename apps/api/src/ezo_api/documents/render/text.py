"""Measure and fit text with the bundled fonts (Liberation Sans ≙ Arial metrics)."""

from __future__ import annotations

from functools import lru_cache

from PIL import ImageFont

from ezo_api.documents import fonts
from ezo_api.documents.render.primitives import TextBox, TextPara

_SCALE = 8  # measure at 8 px per point for sub-point precision
BULLET_INDENT = 1.1  # em
PARAGRAPH_GAP = 0.45  # em, between bullet paragraphs
# PowerPoint and LibreOffice break lines a little differently; keep a safety margin.
WIDTH_SAFETY = 0.96


@lru_cache(maxsize=64)
def _font(size: float, bold: bool) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        str(fonts.BOLD if bold else fonts.REGULAR), max(1, round(size * _SCALE))
    )


def text_width(text: str, size: float, bold: bool = False) -> float:
    return float(_font(round(size, 1), bold).getlength(text)) / _SCALE


def wrap(text: str, width: float, size: float, bold: bool = False) -> list[str]:
    """Greedy word wrap; words longer than a line are broken."""
    lines: list[str] = []
    for raw in text.split("\n"):
        words = raw.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if text_width(candidate, size, bold) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
            while text_width(word, size, bold) > width and len(word) > 1:
                cut = len(word)
                while cut > 1 and text_width(word[:cut], size, bold) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def layout_height(box: TextBox, size: float) -> tuple[float, list[list[str]]]:
    line_h = size * box.line_spacing
    total = 0.0
    all_lines: list[list[str]] = []
    for index, para in enumerate(box.paragraphs):
        para_size = size * para.scale
        indent = para_size * BULLET_INDENT if para.bullet else 0.0
        lines = wrap(para.text, (box.w - indent) * WIDTH_SAFETY, para_size, para.bold or box.bold)
        all_lines.append(lines)
        total += len(lines) * line_h * para.scale
        if index < len(box.paragraphs) - 1:
            total += size * PARAGRAPH_GAP
    return total, all_lines


def fit(box: TextBox) -> TextBox:
    """Choose the largest size (≤ box.size, ≥ box.min_size) at which the text fits."""
    size = box.size
    while True:
        height, lines = layout_height(box, size)
        if height <= box.h or size <= box.min_size:
            box.fitted_size = round(size, 1)
            box.lines = lines
            box.overflow = height > box.h + 0.5
            return box
        size = max(box.min_size, size - 1)


def para(text: str, **kwargs: object) -> TextPara:
    return TextPara(text=text, **kwargs)  # type: ignore[arg-type]


def content_height(box: TextBox) -> float:
    """Height actually used by a fitted box."""
    size = box.fitted_size or box.size
    total = 0.0
    for index, para in enumerate(box.paragraphs):
        lines = box.lines[index] if index < len(box.lines) else []
        total += len(lines) * size * box.line_spacing * para.scale
        if index < len(box.paragraphs) - 1:
            total += size * PARAGRAPH_GAP
    return total
