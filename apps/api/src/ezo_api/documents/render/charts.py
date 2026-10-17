"""Charts and tables as plain primitives for the PNG, PDF and HTML renderers.
(The PPTX renderer uses native, editable PowerPoint charts and tables instead.)"""

from __future__ import annotations

import math
from itertools import pairwise

from ezo_api.documents.render.primitives import (
    Align,
    ChartBox,
    Ellipse,
    Line,
    Primitive,
    Rect,
    TableBox,
    TextBox,
    TextPara,
    Wedge,
)
from ezo_api.documents.render.text import fit


def format_number(value: float) -> str:
    if math.isnan(value):
        return "–"
    if abs(value) >= 1000 and float(value).is_integer():
        return f"{int(value):,}".replace(",", " ")
    if float(value).is_integer():
        return str(int(value))
    return f"{value:,.1f}".replace(",", " ")


def _label(
    x: float,
    y: float,
    w: float,
    h: float,
    value: str,
    size: float,
    color: str,
    align: Align = "center",
    bold: bool = False,
) -> TextBox:
    box = TextBox(
        x,
        y,
        w,
        h,
        [TextPara(value)],
        size=size,
        color=color,
        align=align,
        valign="middle",
        min_size=7,
        bold=bold,
        role="chart_label",
    )
    return fit(box)


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    exponent = 10.0 ** math.floor(math.log10(value))
    for step in (1.0, 2.0, 2.5, 5.0, 10.0):
        if value <= step * exponent:
            return float(step * exponent)
    return float(10 * exponent)


def _legend(chart: ChartBox, names: list[str], y: float) -> list[Primitive]:
    items: list[Primitive] = []
    x = chart.x
    for i, name in enumerate(names):
        color = chart.colors[i % len(chart.colors)]
        items.append(Rect(x, y + 4, 10, 10, fill=color, radius=2))
        label = _label(x + 14, y, 140, 18, name, 11, chart.muted, align="left")
        items.append(label)
        x += 30 + min(140.0, sum(len(line) for lines in label.lines for line in lines) * 6.2)
    return items


def expand_chart(chart: ChartBox, background: str) -> list[Primitive]:
    if chart.kind in ("pie", "doughnut"):
        return _pie(chart, background)
    items: list[Primitive] = []
    names = [name for name, _ in chart.series]
    top = chart.y
    if len(names) > 1:
        items += _legend(chart, names, top)
        top += 26
    values = [v for _, vs in chart.series for v in vs if not math.isnan(v)]
    if not values or not chart.categories:
        return items
    vmax = _nice_max(max(max(values), 0))
    vmin = -_nice_max(-min(values)) if min(values) < 0 else 0.0
    horizontal = chart.kind == "bar"
    axis_w = 56.0 if not horizontal else min(150.0, chart.w * 0.28)
    bottom_h = 30.0 if not horizontal else 22.0
    px, py = chart.x + axis_w, top + 6
    pw, ph = chart.w - axis_w - 8, chart.y + chart.h - bottom_h - py
    n = len(chart.categories)

    def scale(v: float) -> float:
        span = (vmax - vmin) or 1
        return (v - vmin) / span

    # grid + value axis labels
    for i in range(5):
        frac = i / 4
        value = vmin + (vmax - vmin) * frac
        if horizontal:
            gx = px + pw * frac
            items.append(Line(gx, py, gx, py + ph, chart.grid, width=0.75))
            items.append(
                _label(
                    gx - 40, py + ph + 4, 80, 16, format_number(value) + chart.unit, 10, chart.muted
                )
            )
        else:
            gy = py + ph - ph * frac
            items.append(Line(px, gy, px + pw, gy, chart.grid, width=0.75))
            items.append(
                _label(
                    chart.x,
                    gy - 8,
                    axis_w - 8,
                    16,
                    format_number(value) + chart.unit,
                    10,
                    chart.muted,
                    align="right",
                )
            )

    if chart.kind == "line":
        step = pw / max(n - 1, 1)
        for i, category in enumerate(chart.categories):
            items.append(
                _label(px + i * step - step / 2, py + ph + 6, step, 18, category, 11, chart.muted)
            )
        for s_index, (_, series) in enumerate(chart.series):
            color = chart.colors[s_index % len(chart.colors)]
            points = [
                (px + i * step, py + ph - ph * scale(v))
                for i, v in enumerate(series[:n])
                if not math.isnan(v)
            ]
            for (x1, y1), (x2, y2) in pairwise(points):
                items.append(Line(x1, y1, x2, y2, color, width=3))
            for x, y in points:
                items.append(
                    Ellipse(x - 4.5, y - 4.5, 9, 9, fill=color, line=background, line_width=1.5)
                )
        return items

    groups = len(chart.series) or 1
    if horizontal:
        band = ph / n
        bar = min(34.0, band * 0.7 / groups)
        for i, category in enumerate(chart.categories):
            items.append(
                _label(
                    chart.x,
                    py + i * band,
                    axis_w - 10,
                    band,
                    category,
                    12,
                    chart.ink,
                    align="right",
                )
            )
            for s_index, (_, series) in enumerate(chart.series):
                value = series[i] if i < len(series) else float("nan")
                if math.isnan(value):
                    continue
                y = py + i * band + (band - bar * groups) / 2 + s_index * bar
                x0, x1 = px + pw * scale(min(0.0, value)), px + pw * scale(max(0.0, value))
                items.append(
                    Rect(
                        x0,
                        y,
                        max(x1 - x0, 1),
                        bar - 3,
                        fill=chart.colors[s_index % len(chart.colors)],
                        radius=3,
                    )
                )
                if n * groups <= 16:
                    items.append(
                        _label(
                            x1 + 4,
                            y,
                            70,
                            bar - 3,
                            format_number(value),
                            10,
                            chart.ink,
                            align="left",
                        )
                    )
        return items

    band = pw / n
    bar = min(46.0, band * 0.7 / groups)
    zero = py + ph - ph * scale(0)
    for i, category in enumerate(chart.categories):
        items.append(_label(px + i * band, py + ph + 6, band, 20, category, 11, chart.muted))
        for s_index, (_, series) in enumerate(chart.series):
            value = series[i] if i < len(series) else float("nan")
            if math.isnan(value):
                continue
            x = px + i * band + (band - bar * groups) / 2 + s_index * bar
            top_y = py + ph - ph * scale(max(0.0, value))
            bottom_y = py + ph - ph * scale(min(0.0, value))
            items.append(
                Rect(
                    x,
                    top_y,
                    bar - 3,
                    max(bottom_y - top_y, 1),
                    fill=chart.colors[s_index % len(chart.colors)],
                    radius=3,
                )
            )
            if n * groups <= 16:
                items.append(
                    _label(x - 10, top_y - 18, bar + 17, 16, format_number(value), 10, chart.ink)
                )
    items.append(Line(px, zero, px + pw, zero, chart.muted, width=1))
    return items


def _pie(chart: ChartBox, background: str) -> list[Primitive]:
    items: list[Primitive] = []
    values = chart.series[0][1] if chart.series else []
    pairs = [
        (c, v)
        for c, v in zip(chart.categories, values, strict=False)
        if not math.isnan(v) and v > 0
    ]
    total = sum(v for _, v in pairs)
    if not pairs or total <= 0:
        return items
    r = min(chart.h, chart.w * 0.55) / 2 - 6
    cx, cy = chart.x + r + 6, chart.y + chart.h / 2
    angle = -90.0
    for i, (_, value) in enumerate(pairs):
        sweep = 360 * value / total
        items.append(
            Wedge(
                cx,
                cy,
                r,
                angle,
                angle + sweep,
                chart.colors[i % len(chart.colors)],
                inner_r=r * 0.55 if chart.kind == "doughnut" else 0,
            )
        )
        angle += sweep
    lx = cx + r + 30
    row = min(30.0, chart.h / len(pairs))
    for i, (category, value) in enumerate(pairs):
        y = chart.y + (chart.h - row * len(pairs)) / 2 + i * row
        items.append(
            Rect(lx, y + row / 2 - 6, 12, 12, fill=chart.colors[i % len(chart.colors)], radius=3)
        )
        items.append(
            _label(
                lx + 20,
                y,
                chart.x + chart.w - lx - 20,
                row,
                f"{category} — {value / total:.0%}",
                13,
                chart.ink,
                align="left",
            )
        )
    return items


def expand_table(table: TableBox) -> list[Primitive]:
    items: list[Primitive] = []
    columns = max(len(table.header), 1)
    rows = [table.header, *table.rows]
    row_h = table.h / len(rows)
    col_w = table.w / columns
    for r, row in enumerate(rows):
        y = table.y + r * row_h
        fill = table.header_fill if r == 0 else (table.stripe if r % 2 == 0 else None)
        if fill:
            items.append(
                Rect(table.x, y, table.w, row_h, fill=fill, radius=6 if r == 0 else 0, role="table")
            )
        for c in range(columns):
            value = row[c] if c < len(row) else ""
            items.append(
                fit(
                    TextBox(
                        table.x + c * col_w + 10,
                        y + 3,
                        col_w - 20,
                        row_h - 6,
                        [TextPara(value)],
                        size=table.size,
                        color=table.header_ink if r == 0 else table.ink,
                        bold=r == 0,
                        valign="middle",
                        min_size=8,
                        role="table_cell",
                    )
                )
            )
        if r > 0:
            items.append(
                Line(table.x, y, table.x + table.w, y, table.line, width=0.6, role="table")
            )
    return items
