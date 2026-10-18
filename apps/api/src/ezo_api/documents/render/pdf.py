"""Presentations as vector PDF (reportlab), one slide per page."""

from __future__ import annotations

import io
import math

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from ezo_api.documents.pdf.writer import FONT, FONT_BOLD, register_fonts
from ezo_api.documents.render.common import ASCENT, flat, text_lines
from ezo_api.documents.render.primitives import (
    Ellipse,
    ImageBox,
    Line,
    Rect,
    SlidePlan,
    TextBox,
    Wedge,
)
from ezo_api.documents.render.text import BULLET_INDENT


def render_deck_pdf(plans: list[SlidePlan], title: str) -> bytes:
    register_fonts()
    buffer = io.BytesIO()
    first = plans[0]
    c = pdf_canvas.Canvas(buffer, pagesize=(first.width, first.height))
    c.setTitle(title)
    c.setAuthor("EZO")
    for plan in plans:
        h = plan.height
        c.setPageSize((plan.width, h))
        c.setFillColor(HexColor(plan.background))
        c.rect(0, 0, plan.width, h, stroke=0, fill=1)
        for item in flat(plan):
            if isinstance(item, Rect):
                if item.fill:
                    c.setFillColor(HexColor(item.fill))
                if item.line:
                    c.setStrokeColor(HexColor(item.line))
                    c.setLineWidth(item.line_width)
                c.roundRect(
                    item.x,
                    h - item.y - item.h,
                    item.w,
                    item.h,
                    item.radius,
                    stroke=1 if item.line else 0,
                    fill=1 if item.fill else 0,
                )
            elif isinstance(item, Ellipse):
                if item.fill:
                    c.setFillColor(HexColor(item.fill))
                if item.line:
                    c.setStrokeColor(HexColor(item.line))
                    c.setLineWidth(item.line_width)
                c.ellipse(
                    item.x,
                    h - item.y - item.h,
                    item.x + item.w,
                    h - item.y,
                    stroke=1 if item.line else 0,
                    fill=1 if item.fill else 0,
                )
            elif isinstance(item, Line):
                c.setStrokeColor(HexColor(item.color))
                c.setLineWidth(item.width)
                c.line(item.x1, h - item.y1, item.x2, h - item.y2)
                if item.arrow:
                    angle = math.atan2(item.y2 - item.y1, item.x2 - item.x1)
                    size = 6 + item.width * 2
                    path = c.beginPath()
                    path.moveTo(item.x2, h - item.y2)
                    path.lineTo(
                        item.x2 - size * math.cos(angle - 0.45),
                        h - (item.y2 - size * math.sin(angle - 0.45)),
                    )
                    path.lineTo(
                        item.x2 - size * math.cos(angle + 0.45),
                        h - (item.y2 - size * math.sin(angle + 0.45)),
                    )
                    path.close()
                    c.setFillColor(HexColor(item.color))
                    c.drawPath(path, stroke=0, fill=1)
            elif isinstance(item, Wedge):
                c.setFillColor(HexColor(item.fill))
                c.setStrokeColor(HexColor(plan.background))
                c.setLineWidth(1.5)
                c.wedge(
                    item.cx - item.r,
                    h - item.cy - item.r,
                    item.cx + item.r,
                    h - item.cy + item.r,
                    -item.end,
                    item.end - item.start,
                    stroke=1,
                    fill=1,
                )
                if item.inner_r:
                    c.setFillColor(HexColor(plan.background))
                    c.circle(item.cx, h - item.cy, item.inner_r, stroke=0, fill=1)
            elif isinstance(item, ImageBox):
                c.drawImage(
                    ImageReader(io.BytesIO(item.data)), item.x, h - item.y - item.h, item.w, item.h
                )
            elif isinstance(item, TextBox):
                for x, y, line, size, bold, color, bullet in text_lines(item):
                    c.setFillColor(HexColor(color))
                    c.setFont(FONT_BOLD if bold else FONT, size)
                    baseline = h - (y + size * ASCENT)
                    if bullet:
                        c.drawString(x - size * BULLET_INDENT, baseline, "•")
                    c.drawString(x, baseline, line)
        c.showPage()
    c.save()
    return buffer.getvalue()
