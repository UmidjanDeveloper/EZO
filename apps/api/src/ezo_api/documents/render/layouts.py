"""Slide layouts: SlideSpec + Theme → fitted primitives.

Original EZO layouts. Principles: one message per slide, large type, generous
margins (56 pt), a consistent title position, one accent colour at a time,
minimal text, no decorative clutter. Every text box is fitted with real font
metrics; anything that still does not fit is flagged for QA, never hidden.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ezo_api.documents.render.primitives import (
    ChartBox,
    Ellipse,
    Line,
    Primitive,
    Rect,
    SlidePlan,
    TableBox,
    TextBox,
    TextPara,
)
from ezo_api.documents.render.spec import Column, DeckSpec, Node, SlideSpec, Step
from ezo_api.documents.render.text import content_height, fit
from ezo_api.documents.render.theme import TYPE, Theme, mix, readable_on

MARGIN = 56.0
TOP = 44.0
FOOTER_H = 30.0


@dataclass(slots=True)
class Canvas:
    w: float
    h: float
    theme: Theme
    deck_title: str
    index: int
    total: int

    @property
    def inner_w(self) -> float:
        return self.w - 2 * MARGIN

    @property
    def bottom(self) -> float:
        return self.h - FOOTER_H - 14


def canvas_size(aspect_ratio: str) -> tuple[float, float]:
    return (720.0, 540.0) if aspect_ratio == "4:3" else (960.0, 540.0)


def text(
    x: float,
    y: float,
    w: float,
    h: float,
    paragraphs: list[TextPara] | str,
    size: float,
    color: str,
    *,
    bold: bool = False,
    align: str = "left",
    valign: str = "top",
    min_size: float | None = None,
    role: str = "body",
    line_spacing: float = 1.15,
) -> TextBox:
    paras = [TextPara(paragraphs)] if isinstance(paragraphs, str) else paragraphs
    box = TextBox(
        x=x,
        y=y,
        w=w,
        h=h,
        paragraphs=paras,
        size=size,
        color=color,
        bold=bold,
        align=align,  # type: ignore[arg-type]
        valign=valign,  # type: ignore[arg-type]
        line_spacing=line_spacing,
        min_size=min_size if min_size is not None else min(size, TYPE.body_min),
        role=role,
    )
    return fit(box)


def bullets(items: list[str], color: str | None = None) -> list[TextPara]:
    return [TextPara(item, bullet=True, color=color) for item in items]


def title_block(
    c: Canvas, s: SlideSpec, *, w: float | None = None, x: float = MARGIN
) -> tuple[list[Primitive], float]:
    """Kicker + title (+ subtitle) at the standard position. Returns items and the y below."""
    t = c.theme
    width = w if w is not None else c.inner_w
    items: list[Primitive] = []
    y = TOP
    if s.kicker:
        items.append(
            text(
                x,
                y,
                width,
                18,
                s.kicker.upper(),
                TYPE.caption,
                t.accent,
                bold=True,
                role="kicker",
                min_size=10,
            )
        )
        y += 22
    title = text(
        x,
        y,
        width,
        92,
        s.title,
        TYPE.title,
        t.ink,
        bold=True,
        min_size=TYPE.title_min,
        role="title",
        line_spacing=1.08,
    )
    items.append(title)
    used = len([line for lines in title.lines for line in lines]) * title.fitted_size * 1.08
    y += max(used, title.fitted_size * 1.08) + 8
    if s.subtitle:
        sub = text(
            x, y, width, 52, s.subtitle, TYPE.subtitle, t.muted, min_size=14, role="subtitle"
        )
        items.append(sub)
        y += len([line for lines in sub.lines for line in lines]) * sub.fitted_size * 1.15 + 6
    return items, y + 18


def footer(c: Canvas) -> list[Primitive]:
    t = c.theme
    y = c.h - FOOTER_H
    return [
        text(
            MARGIN,
            y,
            c.inner_w * 0.7,
            16,
            c.deck_title,
            TYPE.footer,
            t.muted,
            role="footer",
            min_size=8,
        ),
        text(
            c.w - MARGIN - 60,
            y,
            60,
            16,
            f"{c.index}/{c.total}",
            TYPE.footer,
            t.muted,
            align="right",
            role="footer",
            min_size=8,
        ),
    ]


def card(x: float, y: float, w: float, h: float, t: Theme, *, accent: bool = False) -> Rect:
    fill = mix(t.accent, t.background, 0.88) if accent else t.surface
    return Rect(
        x,
        y,
        w,
        h,
        fill=fill,
        line=None if accent else t.line,
        line_width=0 if accent else 0.75,
        radius=10,
        role="card",
    )


def body_or_bullets(s: SlideSpec) -> list[TextPara]:
    if s.bullets:
        return bullets(s.bullets)
    return [TextPara(s.body)] if s.body else []


# ------------------------------------------------------------------ layouts


def l_cover(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    items: list[Primitive] = []
    # Original geometric composition on the right: overlapping discs (turquoise, lapis, saffron).
    r = c.h * 0.62
    items.append(
        Ellipse(c.w - r * 0.95, c.h * 0.5 - r, r * 2, r * 2, fill=mix(t.accent, t.background, 0.82))
    )
    items.append(Ellipse(c.w - r * 0.62, c.h * 0.18, r * 0.95, r * 0.95, fill=t.accent))
    items.append(Ellipse(c.w - r * 0.98, c.h * 0.58, r * 0.5, r * 0.5, fill=t.accent2))
    items.append(Ellipse(c.w - r * 0.42, c.h * 0.74, r * 0.16, r * 0.16, fill=t.highlight))
    width = c.w * 0.56
    y = c.h * 0.24
    if s.kicker:
        items.append(
            text(
                MARGIN,
                y - 30,
                width,
                20,
                s.kicker.upper(),
                13,
                t.accent,
                bold=True,
                role="kicker",
                min_size=10,
            )
        )
    title = text(
        MARGIN,
        y,
        width,
        190,
        s.title or deck.title,
        50,
        t.ink,
        bold=True,
        min_size=30,
        role="title",
        line_spacing=1.05,
    )
    items.append(title)
    lines = sum(len(lines) for lines in title.lines)
    y += lines * title.fitted_size * 1.05 + 18
    subtitle = s.subtitle or deck.subtitle
    if subtitle:
        items.append(
            text(MARGIN, y, width, 70, subtitle, 22, t.muted, min_size=14, role="subtitle")
        )
    meta = " · ".join(part for part in (deck.author, s.body) if part)
    if meta:
        items.append(
            text(MARGIN, c.h - 74, width, 20, meta, 13, t.muted, role="caption", min_size=10)
        )
    return items


def l_title_subtitle(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    items: list[Primitive] = [Rect(c.w / 2 - 24, c.h * 0.3, 48, 5, fill=t.accent, radius=2)]
    items.append(
        text(
            MARGIN * 2,
            c.h * 0.34,
            c.w - 4 * MARGIN,
            130,
            s.title,
            44,
            t.ink,
            bold=True,
            align="center",
            valign="middle",
            min_size=28,
            role="title",
            line_spacing=1.05,
        )
    )
    if s.subtitle or s.body:
        items.append(
            text(
                MARGIN * 2,
                c.h * 0.6,
                c.w - 4 * MARGIN,
                80,
                s.subtitle or s.body,
                22,
                t.muted,
                align="center",
                min_size=14,
                role="subtitle",
            )
        )
    return items + footer(c)


def l_section(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    ink = readable_on(t.accent)
    items: list[Primitive] = [Rect(0, 0, c.w, c.h, fill=t.accent, role="background")]
    items.append(
        Ellipse(
            c.w * 0.72,
            -c.h * 0.25,
            c.h * 0.9,
            c.h * 0.9,
            fill=mix(t.accent, "#FFFFFF" if ink == "#16202B" else "#000000", 0.12),
        )
    )
    if s.kicker:
        items.append(
            text(
                MARGIN,
                c.h * 0.32,
                c.w * 0.6,
                30,
                s.kicker.upper(),
                16,
                ink,
                bold=True,
                role="kicker",
                min_size=12,
            )
        )
    items.append(
        text(
            MARGIN,
            c.h * 0.4,
            c.w * 0.7,
            150,
            s.title,
            48,
            ink,
            bold=True,
            min_size=30,
            role="title",
            line_spacing=1.05,
        )
    )
    if s.subtitle:
        items.append(
            text(
                MARGIN,
                c.h * 0.72,
                c.w * 0.62,
                60,
                s.subtitle,
                20,
                ink,
                min_size=14,
                role="subtitle",
            )
        )
    return items


def l_bullets(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    paras = body_or_bullets(s)
    items = head
    if paras:
        items.append(
            text(
                MARGIN, y, c.inner_w * 0.82, c.bottom - y, paras, TYPE.body, t.ink, line_spacing=1.2
            )
        )
    return items + footer(c)


def l_hero_image(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    split = c.w * 0.5
    head, y = title_block(c, s, w=split - MARGIN - 20)
    items = head
    paras = body_or_bullets(s)
    if paras:
        items.append(text(MARGIN, y, split - MARGIN - 20, c.bottom - y, paras, 20, t.ink))
    # Visual panel: an abstract composition until the VisualAgent generates images.
    px, py, pw, ph = split + 10, TOP, c.w - split - MARGIN - 10, c.h - TOP - FOOTER_H - 20
    items.append(
        Rect(px, py, pw, ph, fill=mix(t.accent2, t.background, 0.85), radius=14, role="visual")
    )
    items.append(
        Ellipse(
            px + pw * 0.15,
            py + ph * 0.2,
            pw * 0.7,
            pw * 0.7,
            fill=mix(t.accent, t.background, 0.35),
            role="visual",
        )
    )
    items.append(
        Ellipse(px + pw * 0.5, py + ph * 0.5, pw * 0.38, pw * 0.38, fill=t.accent2, role="visual")
    )
    items.append(
        Rect(px + pw * 0.1, py + ph - 26, pw * 0.3, 6, fill=t.highlight, radius=3, role="visual")
    )
    return items + footer(c)


def l_big_number(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    metric = s.metric or (s.metrics[0] if s.metrics else None)
    items: list[Primitive] = []
    if s.title:
        items.append(
            text(
                MARGIN, TOP, c.inner_w, 50, s.title, 26, t.ink, bold=True, min_size=20, role="title"
            )
        )
    value = metric.value if metric else ""
    items.append(
        text(
            MARGIN,
            c.h * 0.24,
            c.inner_w * 0.75,
            150,
            value,
            TYPE.huge,
            t.accent,
            bold=True,
            min_size=48,
            role="metric",
            line_spacing=1.0,
        )
    )
    label = metric.label if metric else s.subtitle
    if label:
        items.append(
            text(
                MARGIN,
                c.h * 0.54,
                c.inner_w * 0.7,
                70,
                label,
                26,
                t.ink,
                min_size=16,
                role="metric_label",
            )
        )
    if s.body:
        items.append(
            text(
                MARGIN,
                c.h * 0.7,
                c.inner_w * 0.7,
                60,
                s.body,
                16,
                t.muted,
                min_size=12,
                role="caption",
            )
        )
    return items + footer(c)


def l_kpi(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    metrics = s.metrics or ([s.metric] if s.metric else [])
    n = max(len(metrics), 1)
    gap = 20.0
    w = (c.inner_w - gap * (n - 1)) / n
    h = min(200.0, c.bottom - y - 10)
    for i, m in enumerate(metrics):
        x = MARGIN + i * (w + gap)
        items.append(card(x, y, w, h, t))
        items.append(Rect(x, y, 6, h, fill=t.chart[i % len(t.chart)], radius=3))
        items.append(
            text(
                x + 24,
                y + 22,
                w - 40,
                70,
                m.value,
                46,
                t.ink,
                bold=True,
                min_size=24,
                role="metric",
                line_spacing=1.0,
            )
        )
        items.append(
            text(
                x + 24,
                y + 100,
                w - 40,
                h - 116,
                m.label,
                16,
                t.muted,
                min_size=12,
                role="metric_label",
            )
        )
    if s.body:
        items.append(
            text(
                MARGIN,
                y + h + 18,
                c.inner_w,
                c.bottom - (y + h + 18),
                s.body,
                16,
                t.muted,
                min_size=12,
                role="caption",
            )
        )
    return items + footer(c)


def l_quote(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    items: list[Primitive] = [
        text(
            MARGIN,
            TOP + 10,
            100,
            110,
            "“",
            120,
            t.accent,
            bold=True,
            role="decor",
            min_size=60,
            line_spacing=1.0,
        )
    ]
    items.append(
        text(
            MARGIN + 40,
            c.h * 0.28,
            c.inner_w - 80,
            200,
            s.quote or s.body or s.title,
            32,
            t.ink,
            min_size=18,
            role="quote",
            line_spacing=1.2,
        )
    )
    if s.author:
        items.append(
            text(
                MARGIN + 40,
                c.h * 0.72,
                c.inner_w - 80,
                30,
                f"— {s.author}",
                18,
                t.muted,
                min_size=12,
                role="caption",
            )
        )
    return items + footer(c)


PANEL_TOP = 96.0  # space for the colour mark and the column title inside a card
MIN_CARD_H = 170.0


def _column_panel(
    x: float, y: float, w: float, h: float, col: Column, t: Theme, *, accent: bool, color: str
) -> tuple[list[Primitive], float]:
    """A card with a title and bullets; returns the items and the height the content needs."""
    items: list[Primitive] = [card(x, y, w, h, t, accent=accent)]
    items.append(Rect(x + 22, y + 22, 34, 4, fill=color, radius=2))
    items.append(
        text(
            x + 22,
            y + 36,
            w - 44,
            56,
            col.title,
            21,
            t.ink,
            bold=True,
            min_size=15,
            role="column_title",
        )
    )
    needed = PANEL_TOP
    if col.bullets:
        body = text(
            x + 22,
            y + PANEL_TOP,
            w - 44,
            h - PANEL_TOP - 20,
            bullets(col.bullets),
            20,
            t.ink,
            min_size=12,
        )
        items.append(body)
        needed += content_height(body)
    return items, needed + 26


def _row_of_panels(panels: list[tuple[list[Primitive], float]], avail: float) -> list[Primitive]:
    """Cards in a row share one height: what the fullest card needs, not the whole slide."""
    height = min(avail, max([MIN_CARD_H, *(needed for _, needed in panels)]))
    # Short content: place the row a little above the middle of the free space.
    offset = max(0.0, (avail - height) * 0.3)
    out: list[Primitive] = []
    for items, _ in panels:
        for item in items:
            if isinstance(item, Rect) and item.role == "card":
                item.h = height
            elif isinstance(item, TextBox) and item.role == "body":
                item.h = max(height - PANEL_TOP - 20, 1.0)
            if isinstance(item, Rect | TextBox):
                item.y += offset
        out += items
    return out


def _columns(s: SlideSpec, n: int) -> list[Column]:
    if s.columns:
        return s.columns[:n]
    per = max(1, math.ceil(len(s.bullets) / n))
    return [
        Column(title="", bullets=s.bullets[i * per : (i + 1) * per])
        for i in range(n)
        if s.bullets[i * per : (i + 1) * per]
    ]


def l_columns(c: Canvas, s: SlideSpec, deck: DeckSpec, n: int) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    cols = _columns(s, n)
    gap = 22.0
    count = max(len(cols), 1)
    w = (c.inner_w - gap * (count - 1)) / count
    panels = [
        _column_panel(
            MARGIN + i * (w + gap),
            y,
            w,
            c.bottom - y,
            col,
            t,
            accent=False,
            color=t.chart[i % len(t.chart)],
        )
        for i, col in enumerate(cols)
    ]
    return items + _row_of_panels(panels, c.bottom - y) + footer(c)


def l_two_column(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    return l_columns(c, s, deck, 2)


def l_three_column(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    return l_columns(c, s, deck, 3)


def _pair(
    c: Canvas, s: SlideSpec, left_label: str, right_label: str, *, arrow: bool
) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    cols = [*_columns(s, 2), Column(), Column()]
    left, right = cols[0], cols[1]
    left = Column(title=left.title or left_label, bullets=left.bullets)
    right = Column(title=right.title or right_label, bullets=right.bullets)
    gap = 60.0 if arrow else 24.0
    w = (c.inner_w - gap) / 2
    avail = c.bottom - y
    panels = [
        _column_panel(MARGIN, y, w, avail, left, t, accent=False, color=t.muted),
        _column_panel(MARGIN + w + gap, y, w, avail, right, t, accent=True, color=t.accent),
    ]
    row = _row_of_panels(panels, avail)
    items += row
    first_card = next(item for item in row if isinstance(item, Rect) and item.role == "card")
    if arrow:
        cx, cy = MARGIN + w + gap / 2, first_card.y + first_card.h / 2
        items.append(Line(cx - 18, cy, cx + 18, cy, t.accent, width=3, arrow=True))
    return items + footer(c)


def l_comparison(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    return _pair(c, s, "A", "B", arrow=False)


def l_before_after(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    labels = {"uz": ("Hozir", "Keyin"), "en": ("Before", "After"), "ru": ("Сейчас", "После")}[
        deck.language
    ]
    return _pair(c, s, labels[0], labels[1], arrow=True)


def l_problem_solution(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    labels = {
        "uz": ("Muammo", "Yechim"),
        "en": ("Problem", "Solution"),
        "ru": ("Проблема", "Решение"),
    }[deck.language]
    return _pair(c, s, labels[0], labels[1], arrow=True)


def _steps(s: SlideSpec) -> list[Step]:
    if s.steps:
        return s.steps
    return [Step(label=str(i + 1), text=b) for i, b in enumerate(s.bullets[:6])]


def l_timeline(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    steps = _steps(s)
    n = max(len(steps), 1)
    line_y = y + (c.bottom - y) * 0.5 - 30  # the timeline sits in the middle of the free space
    items.append(Line(MARGIN, line_y, c.w - MARGIN, line_y, t.line, width=2))
    slot = c.inner_w / n
    for i, step in enumerate(steps):
        cx = MARGIN + slot * (i + 0.5)
        color = t.chart[i % len(t.chart)]
        items.append(Ellipse(cx - 9, line_y - 9, 18, 18, fill=color))
        items.append(
            text(
                cx - slot / 2 + 6,
                line_y - 62,
                slot - 12,
                40,
                step.label,
                22,
                color,
                bold=True,
                align="center",
                valign="bottom",
                min_size=12,
                role="step_label",
            )
        )
        items.append(
            text(
                cx - slot / 2 + 6,
                line_y + 22,
                slot - 12,
                c.bottom - line_y - 22,
                step.text,
                15,
                t.ink,
                align="center",
                min_size=11,
            )
        )
    return items + footer(c)


def l_process(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    steps = _steps(s)
    n = max(len(steps), 1)
    gap = 26.0
    w = (c.inner_w - gap * (n - 1)) / n
    h = min(230.0, c.bottom - y)
    for i, step in enumerate(steps):
        x = MARGIN + i * (w + gap)
        items.append(card(x, y, w, h, t, accent=i == n - 1))
        items.append(Ellipse(x + 18, y + 18, 36, 36, fill=t.accent))
        items.append(
            text(
                x + 18,
                y + 18,
                36,
                36,
                str(i + 1),
                17,
                readable_on(t.accent),
                bold=True,
                align="center",
                valign="middle",
                min_size=12,
                role="badge",
            )
        )
        items.append(
            text(
                x + 18,
                y + 66,
                w - 36,
                48,
                step.label,
                18,
                t.ink,
                bold=True,
                min_size=12,
                role="step_label",
            )
        )
        items.append(text(x + 18, y + 116, w - 36, h - 130, step.text, 14.5, t.muted, min_size=11))
        if i < n - 1:
            ax = x + w + 4
            items.append(
                Line(ax, y + h / 2, ax + gap - 8, y + h / 2, t.accent, width=2.5, arrow=True)
            )
    return items + footer(c)


def l_roadmap(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    steps = _steps(s)
    n = max(len(steps), 1)
    w = c.inner_w / n
    bar_y = y + 4
    for i, step in enumerate(steps):
        x = MARGIN + i * w
        shade = mix(t.accent, t.background, 0.75 - 0.6 * (i / max(n - 1, 1)))
        items.append(Rect(x + 2, bar_y, w - 4, 44, fill=shade, radius=8))
        items.append(
            text(
                x + 14,
                bar_y + 4,
                w - 28,
                36,
                step.label,
                17,
                readable_on(shade),
                bold=True,
                valign="middle",
                min_size=11,
                role="step_label",
            )
        )
        items.append(
            text(
                x + 10, bar_y + 62, w - 20, c.bottom - bar_y - 62, step.text, 15, t.ink, min_size=11
            )
        )
    return items + footer(c)


def l_architecture(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    nodes = s.nodes or [Node(id=str(i), label=b) for i, b in enumerate(s.bullets[:8])]
    if not nodes:
        return items + footer(c)
    ids = [n.id for n in nodes]
    # Layer nodes left→right by longest path from sources (simple, cycle-safe).
    level = dict.fromkeys(ids, 0)
    for _ in range(len(ids)):
        for a, b in s.edges:
            if a in level and b in level and level[b] < level[a] + 1 <= len(ids):
                level[b] = level[a] + 1
    layers: dict[int, list[str]] = {}
    for node_id in ids:
        layers.setdefault(level[node_id], []).append(node_id)
    cols = max(layers) + 1
    col_w = c.inner_w / cols
    box_w = min(col_w - 40, 220.0)
    area_h = c.bottom - y
    pos: dict[str, tuple[float, float, float, float]] = {}
    for col, members in layers.items():
        box_h = min(70.0, area_h / len(members) - 18)
        step = area_h / len(members)
        for row, node_id in enumerate(members):
            bx = MARGIN + col * col_w + (col_w - box_w) / 2
            by = y + row * step + (step - box_h) / 2
            pos[node_id] = (bx, by, box_w, box_h)
    for a, b in s.edges:
        if a in pos and b in pos:
            ax, ay, aw, ah = pos[a]
            bx, by, bw, bh = pos[b]
            items.append(
                Line(ax + aw, ay + ah / 2, bx - 4, by + bh / 2, t.muted, width=1.75, arrow=True)
            )
    labels = {n.id: n.label or n.id for n in nodes}
    for node_id in ids:
        bx, by, bw, bh = pos[node_id]
        items.append(
            Rect(
                bx,
                by,
                bw,
                bh,
                fill=t.surface,
                line=t.chart[level[node_id] % len(t.chart)],
                line_width=2,
                radius=10,
                role="node",
            )
        )
        items.append(
            text(
                bx + 10,
                by + 6,
                bw - 20,
                bh - 12,
                labels[node_id],
                16,
                t.ink,
                bold=True,
                align="center",
                valign="middle",
                min_size=10,
                role="node_label",
            )
        )
    return items + footer(c)


def _chart_box(c: Canvas, s: SlideSpec, x: float, y: float, w: float, h: float) -> ChartBox | None:
    t = c.theme
    if s.chart is None:
        return None
    return ChartBox(
        x=x,
        y=y,
        w=w,
        h=h,
        kind=s.chart.type,
        categories=s.chart.categories,
        series=[(series.name, series.values) for series in s.chart.series],
        colors=list(t.chart),
        ink=t.ink,
        muted=t.muted,
        grid=t.line,
        unit=s.chart.unit,
    )


def l_chart(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    paras = body_or_bullets(s)
    chart_w = c.inner_w * (0.64 if paras else 1.0)
    chart = _chart_box(c, s, MARGIN, y, chart_w, c.bottom - y)
    if chart:
        items.append(chart)
    if paras:
        x = MARGIN + chart_w + 28
        items.append(
            text(x, y + 10, c.w - MARGIN - x, c.bottom - y - 10, paras, 17, t.ink, min_size=12)
        )
    if s.chart and s.chart.source:
        items.append(
            text(
                MARGIN,
                c.bottom + 2,
                c.inner_w,
                14,
                s.chart.source,
                9,
                t.muted,
                role="caption",
                min_size=8,
            )
        )
    return items + footer(c)


def l_table(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    if s.table and s.table.headers:
        rows = len(s.table.rows) + 1
        h = min(c.bottom - y, 34.0 * rows + 6)
        items.append(
            TableBox(
                x=MARGIN,
                y=y,
                w=c.inner_w,
                h=h,
                header=s.table.headers,
                rows=[
                    (r + [""] * len(s.table.headers))[: len(s.table.headers)] for r in s.table.rows
                ],
                size=15 if rows <= 7 else 12,
                ink=t.ink,
                header_fill=t.accent,
                header_ink=readable_on(t.accent),
                stripe=mix(t.accent, t.background, 0.93),
                line=t.line,
            )
        )
    return items + footer(c)


def l_market(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    metrics = (s.metrics or [])[:3]
    size = c.bottom - y
    cx = MARGIN + size / 2 + 10
    cy = y + size / 2
    for i, scale in enumerate((1.0, 0.68, 0.38)[: max(len(metrics), 1)]):
        r = size / 2 * scale
        fill = mix(t.accent, t.background, 0.82 - i * 0.3)
        items.append(Ellipse(cx - r, cy + size / 2 - 2 * r, 2 * r, 2 * r, fill=fill))
    tx = MARGIN + size + 50
    labels = ("TAM", "SAM", "SOM")
    row_h = size / max(len(metrics), 1)
    for i, m in enumerate(metrics):
        ry = y + i * row_h
        items.append(
            text(tx, ry + 4, 90, 26, labels[i], 14, t.accent, bold=True, min_size=10, role="kicker")
        )
        items.append(
            text(
                tx,
                ry + 26,
                c.w - MARGIN - tx,
                48,
                m.value,
                34,
                t.ink,
                bold=True,
                min_size=18,
                role="metric",
            )
        )
        items.append(
            text(tx, ry + 72, c.w - MARGIN - tx, row_h - 76, m.label, 14, t.muted, min_size=10)
        )
    return items + footer(c)


def l_product(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    split = c.w * 0.46
    head, y = title_block(c, s, x=split + 10, w=c.w - split - MARGIN - 10)
    items = head
    paras = body_or_bullets(s)
    if paras:
        items.append(
            text(
                split + 10,
                y,
                c.w - split - MARGIN - 10,
                c.bottom - y,
                paras,
                19,
                t.ink,
                min_size=12,
            )
        )
    # Abstract product frame (a window with content blocks) — original illustration.
    fx, fy, fw, fh = MARGIN, TOP + 10, split - MARGIN - 20, c.h - TOP - FOOTER_H - 40
    items.append(
        Rect(fx, fy, fw, fh, fill=t.surface, line=t.line, line_width=1, radius=14, role="visual")
    )
    items.append(
        Rect(fx, fy, fw, 30, fill=mix(t.accent, t.background, 0.85), radius=14, role="visual")
    )
    for i, color in enumerate((t.highlight, t.accent2, t.accent)):
        items.append(Ellipse(fx + 14 + i * 16, fy + 10, 10, 10, fill=color, role="visual"))
    items.append(
        Rect(
            fx + 24,
            fy + 54,
            fw * 0.55,
            16,
            fill=mix(t.ink, t.surface, 0.8),
            radius=4,
            role="visual",
        )
    )
    items.append(
        Rect(
            fx + 24,
            fy + 82,
            fw * 0.75,
            10,
            fill=mix(t.ink, t.surface, 0.9),
            radius=3,
            role="visual",
        )
    )
    for i in range(3):
        bw = (fw - 48 - 2 * 14) / 3
        items.append(
            Rect(
                fx + 24 + i * (bw + 14),
                fy + 112,
                bw,
                fh - 140,
                fill=mix(t.chart[i], t.surface, 0.75),
                radius=8,
                role="visual",
            )
        )
    return items + footer(c)


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "•"


def l_team(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    members = s.columns or [Column(title=b, bullets=[]) for b in s.bullets]
    n = max(len(members[:4]), 1)
    gap = 22.0
    w = (c.inner_w - gap * (n - 1)) / n
    card_h = min(c.bottom - y, 250.0)
    for i, member in enumerate(members[:4]):
        x = MARGIN + i * (w + gap)
        items.append(card(x, y, w, card_h, t))
        d = min(84.0, w * 0.4)
        color = t.chart[i % len(t.chart)]
        items.append(Ellipse(x + (w - d) / 2, y + 24, d, d, fill=color))
        items.append(
            text(
                x + (w - d) / 2,
                y + 24,
                d,
                d,
                _initials(member.title),
                26,
                readable_on(color),
                bold=True,
                align="center",
                valign="middle",
                min_size=14,
                role="badge",
            )
        )
        items.append(
            text(
                x + 14,
                y + 36 + d,
                w - 28,
                50,
                member.title,
                18,
                t.ink,
                bold=True,
                align="center",
                min_size=12,
                role="name",
            )
        )
        if member.bullets:
            items.append(
                text(
                    x + 14,
                    y + 90 + d,
                    w - 28,
                    card_h - 100 - d,
                    [TextPara(b) for b in member.bullets],
                    14,
                    t.muted,
                    align="center",
                    min_size=10,
                )
            )
    return items + footer(c)


def l_financial(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    head, y = title_block(c, s)
    items = head
    metrics = (s.metrics or [])[:3]
    chart_w = c.inner_w * (0.62 if metrics else 1.0)
    chart = _chart_box(c, s, MARGIN, y, chart_w, c.bottom - y)
    if chart:
        items.append(chart)
    elif s.table:
        return l_table(c, s, deck)
    x = MARGIN + chart_w + 28
    row_h = (c.bottom - y) / max(len(metrics), 1)
    for i, m in enumerate(metrics):
        ry = y + i * row_h
        items.append(Rect(x, ry + 6, 4, row_h - 18, fill=t.chart[i % len(t.chart)], radius=2))
        items.append(
            text(
                x + 16,
                ry + 4,
                c.w - MARGIN - x - 16,
                44,
                m.value,
                30,
                t.ink,
                bold=True,
                min_size=16,
                role="metric",
            )
        )
        items.append(
            text(
                x + 16,
                ry + 46,
                c.w - MARGIN - x - 16,
                row_h - 54,
                m.label,
                13,
                t.muted,
                min_size=10,
            )
        )
    return items + footer(c)


def l_closing(c: Canvas, s: SlideSpec, deck: DeckSpec) -> list[Primitive]:
    t = c.theme
    ink = readable_on(t.accent)
    items: list[Primitive] = [Rect(0, 0, c.w, c.h, fill=t.accent, role="background")]
    items.append(
        Ellipse(-c.h * 0.3, c.h * 0.45, c.h * 0.9, c.h * 0.9, fill=mix(t.accent, t.accent2, 0.35))
    )
    items.append(
        text(
            MARGIN * 2,
            c.h * 0.28,
            c.w - 4 * MARGIN,
            140,
            s.title,
            48,
            ink,
            bold=True,
            align="center",
            valign="middle",
            min_size=28,
            role="title",
            line_spacing=1.05,
        )
    )
    detail = s.subtitle or s.body
    if detail:
        items.append(
            text(
                MARGIN * 2,
                c.h * 0.58,
                c.w - 4 * MARGIN,
                80,
                detail,
                20,
                ink,
                align="center",
                min_size=13,
                role="subtitle",
            )
        )
    if s.bullets:
        items.append(
            text(
                MARGIN * 2,
                c.h * 0.74,
                c.w - 4 * MARGIN,
                60,
                " · ".join(s.bullets),
                15,
                ink,
                align="center",
                min_size=11,
                role="caption",
            )
        )
    return items


LAYOUTS = {
    "cover": l_cover,
    "title_subtitle": l_title_subtitle,
    "section": l_section,
    "hero_image": l_hero_image,
    "big_number": l_big_number,
    "kpi": l_kpi,
    "quote": l_quote,
    "two_column": l_two_column,
    "three_column": l_three_column,
    "comparison": l_comparison,
    "before_after": l_before_after,
    "timeline": l_timeline,
    "process": l_process,
    "roadmap": l_roadmap,
    "architecture": l_architecture,
    "chart": l_chart,
    "table": l_table,
    "problem_solution": l_problem_solution,
    "market": l_market,
    "product": l_product,
    "team": l_team,
    "financial": l_financial,
    "closing": l_closing,
    "bullets": l_bullets,
}


def layout_deck(deck: DeckSpec, theme: Theme) -> list[SlidePlan]:
    w, h = canvas_size(deck.aspect_ratio)
    plans = []
    total = len(deck.slides)
    for index, slide in enumerate(deck.slides, start=1):
        c = Canvas(w, h, theme, deck.title, index, total)
        items = LAYOUTS[slide.layout](c, slide, deck)
        plans.append(
            SlidePlan(
                index=index,
                layout=slide.layout,
                title=slide.title,
                width=w,
                height=h,
                background=theme.background,
                items=items,
                notes=slide.speaker_notes,
            )
        )
    return plans
