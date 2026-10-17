"""Drawing primitives: every slide is laid out once into these, then rendered to
PPTX, PNG, PDF or HTML. Coordinates are points from the top-left corner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Align = Literal["left", "center", "right"]
VAlign = Literal["top", "middle", "bottom"]


@dataclass(slots=True)
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: str | None
    line: str | None = None
    line_width: float = 0.0
    radius: float = 0.0
    role: str = "decor"


@dataclass(slots=True)
class Ellipse:
    x: float
    y: float
    w: float
    h: float
    fill: str | None
    line: str | None = None
    line_width: float = 0.0
    role: str = "decor"


@dataclass(slots=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    color: str
    width: float = 1.5
    arrow: bool = False
    role: str = "decor"


@dataclass(slots=True)
class Wedge:
    """A pie/doughnut slice (angles in degrees, 0 = 3 o'clock, clockwise)."""

    cx: float
    cy: float
    r: float
    start: float
    end: float
    fill: str
    inner_r: float = 0.0
    role: str = "chart"


@dataclass(slots=True)
class TextPara:
    text: str
    bullet: bool = False
    bold: bool = False
    color: str | None = None
    scale: float = 1.0


@dataclass(slots=True)
class TextBox:
    x: float
    y: float
    w: float
    h: float
    paragraphs: list[TextPara]
    size: float
    color: str
    bold: bool = False
    align: Align = "left"
    valign: VAlign = "top"
    line_spacing: float = 1.15
    min_size: float = 12.0
    role: str = "body"
    # Filled by the fitter:
    fitted_size: float = 0.0
    lines: list[list[str]] = field(default_factory=list)
    overflow: bool = False


@dataclass(slots=True)
class ChartBox:
    x: float
    y: float
    w: float
    h: float
    kind: str
    categories: list[str]
    series: list[tuple[str, list[float]]]
    colors: list[str]
    ink: str
    muted: str
    grid: str
    unit: str = ""
    role: str = "chart"


@dataclass(slots=True)
class TableBox:
    x: float
    y: float
    w: float
    h: float
    header: list[str]
    rows: list[list[str]]
    size: float
    ink: str
    header_fill: str
    header_ink: str
    stripe: str
    line: str
    role: str = "table"


Primitive = Rect | Ellipse | Line | Wedge | TextBox | ChartBox | TableBox


@dataclass(slots=True)
class SlidePlan:
    index: int
    layout: str
    title: str
    width: float
    height: float
    background: str
    items: list[Primitive]
    notes: str = ""
