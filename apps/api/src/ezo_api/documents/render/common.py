"""Helpers shared by the renderers."""

from __future__ import annotations

from collections.abc import Iterator

from ezo_api.documents.render.charts import expand_chart, expand_table
from ezo_api.documents.render.primitives import ChartBox, Primitive, SlidePlan, TableBox, TextBox
from ezo_api.documents.render.text import BULLET_INDENT, PARAGRAPH_GAP, text_width

ASCENT = 0.905  # Liberation Sans / Arial ascender as a fraction of the font size


def flat(plan: SlidePlan) -> Iterator[Primitive]:
    """Primitives with charts and tables expanded (for PNG, PDF, HTML)."""
    for item in plan.items:
        if isinstance(item, ChartBox):
            yield from expand_chart(item, plan.background)
        elif isinstance(item, TableBox):
            yield from expand_table(item)
        else:
            yield item


def text_lines(box: TextBox) -> Iterator[tuple[float, float, str, float, bool, str, bool]]:
    """Positioned lines of a fitted text box: (x, top, text, size, bold, color, is_bullet_start)."""
    size = box.fitted_size or box.size
    line_h = size * box.line_spacing
    heights = []
    for index, para in enumerate(box.paragraphs):
        lines = box.lines[index] if index < len(box.lines) else []
        h = len(lines) * line_h * para.scale
        heights.append(h + (size * PARAGRAPH_GAP if index < len(box.paragraphs) - 1 else 0))
    total = sum(heights)
    if box.valign == "middle":
        y = box.y + max(0.0, (box.h - total) / 2)
    elif box.valign == "bottom":
        y = box.y + max(0.0, box.h - total)
    else:
        y = box.y
    for index, para in enumerate(box.paragraphs):
        lines = box.lines[index] if index < len(box.lines) else []
        para_size = size * para.scale
        indent = para_size * BULLET_INDENT if para.bullet else 0.0
        color = para.color or box.color
        bold = para.bold or box.bold
        for line_no, line in enumerate(lines):
            width = text_width(line, para_size, bold)
            if box.align == "center":
                x = box.x + indent + (box.w - indent - width) / 2
            elif box.align == "right":
                x = box.x + box.w - width
            else:
                x = box.x + indent
            yield x, y, line, para_size, bold, color, para.bullet and line_no == 0
            y += para_size * box.line_spacing
        y += size * PARAGRAPH_GAP if index < len(box.paragraphs) - 1 else 0
