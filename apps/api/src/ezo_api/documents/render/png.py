"""Slide previews as PNG (Pillow)."""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

from ezo_api.documents import fonts
from ezo_api.documents.render.common import ASCENT, flat, text_lines
from ezo_api.documents.render.primitives import Ellipse, Line, Rect, SlidePlan, TextBox, Wedge
from ezo_api.documents.render.text import BULLET_INDENT

_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def _font(px: int, bold: bool) -> ImageFont.FreeTypeFont:
    key = (max(px, 1), bold)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(fonts.BOLD if bold else fonts.REGULAR), key[0])
    return _cache[key]


def render_png(plan: SlidePlan, width_px: int = 1280) -> bytes:
    k = width_px / plan.width
    image = Image.new("RGB", (width_px, round(plan.height * k)), plan.background)
    draw = ImageDraw.Draw(image)
    for item in flat(plan):
        if isinstance(item, Rect):
            box = [item.x * k, item.y * k, (item.x + item.w) * k, (item.y + item.h) * k]
            draw.rounded_rectangle(
                box,
                radius=item.radius * k,
                fill=item.fill,
                outline=item.line,
                width=max(1, round(item.line_width * k)) if item.line else 0,
            )
        elif isinstance(item, Ellipse):
            draw.ellipse(
                [item.x * k, item.y * k, (item.x + item.w) * k, (item.y + item.h) * k],
                fill=item.fill,
                outline=item.line,
                width=max(1, round(item.line_width * k)) if item.line else 0,
            )
        elif isinstance(item, Line):
            draw.line(
                [item.x1 * k, item.y1 * k, item.x2 * k, item.y2 * k],
                fill=item.color,
                width=max(1, round(item.width * k)),
            )
            if item.arrow:
                angle = math.atan2(item.y2 - item.y1, item.x2 - item.x1)
                size = (6 + item.width * 2) * k
                tip = (item.x2 * k, item.y2 * k)
                left = (
                    tip[0] - size * math.cos(angle - 0.45),
                    tip[1] - size * math.sin(angle - 0.45),
                )
                right = (
                    tip[0] - size * math.cos(angle + 0.45),
                    tip[1] - size * math.sin(angle + 0.45),
                )
                draw.polygon([tip, left, right], fill=item.color)
        elif isinstance(item, Wedge):
            bbox = [
                (item.cx - item.r) * k,
                (item.cy - item.r) * k,
                (item.cx + item.r) * k,
                (item.cy + item.r) * k,
            ]
            draw.pieslice(
                bbox,
                item.start,
                item.end,
                fill=item.fill,
                outline=plan.background,
                width=max(1, round(1.5 * k)),
            )
            if item.inner_r:
                r = item.inner_r
                draw.ellipse(
                    [(item.cx - r) * k, (item.cy - r) * k, (item.cx + r) * k, (item.cy + r) * k],
                    fill=plan.background,
                )
        elif isinstance(item, TextBox):
            for x, y, line, size, bold, color, bullet in text_lines(item):
                font = _font(round(size * k), bold)
                baseline = (y + size * ASCENT) * k
                if bullet:
                    draw.text(
                        ((x - size * BULLET_INDENT) * k, baseline),
                        "•",
                        font=font,
                        fill=color,
                        anchor="ls",
                    )
                draw.text((x * k, baseline), line, font=font, fill=color, anchor="ls")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
