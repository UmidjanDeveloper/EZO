"""Graphics EZO lays out itself: diagrams, social graphics and logo concept sheets.

Image models misspell text, so EZO never asks them for words. The model
(optionally) supplies a picture — a background or a symbol — and EZO's own layout
engine draws every word with real fonts. Without an image provider these
graphics still work: the picture becomes an abstract composition, and the
artifact is marked as a placeholder (``placeholder: true``) so nobody mistakes
it for a generated image.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ezo_api.documents.render.html import slide_svg
from ezo_api.documents.render.layouts import MARGIN, layout_deck, text
from ezo_api.documents.render.png import render_png
from ezo_api.documents.render.primitives import (
    Ellipse,
    ImageBox,
    Primitive,
    Rect,
    SlidePlan,
    TextBox,
)
from ezo_api.documents.render.spec import DeckSpec, Node, SlideSpec, Step
from ezo_api.documents.render.theme import THEMES, Theme, mix, readable_on
from ezo_api.visual.images import cover_fit

GraphicKind = Literal["diagram", "social", "logo"]
DiagramKind = Literal["flow", "architecture", "process", "timeline"]
SocialFormat = Literal["square", "portrait", "story", "landscape"]

# Canvas size in points, the aspect ratio to request from an image model, PNG width.
SOCIAL_FORMATS: dict[str, tuple[float, float, str, int]] = {
    "square": (540.0, 540.0, "1:1", 1080),
    "portrait": (432.0, 540.0, "4:5", 1080),
    "story": (303.75, 540.0, "9:16", 1080),
    "landscape": (960.0, 540.0, "16:9", 1600),
}
LOGO_SIZE = 540.0


def _short(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _theme(name: str) -> Theme:
    return THEMES.get(name) or THEMES["ezo"]


class DiagramSpec(BaseModel):
    title: str = ""
    kind: DiagramKind = "flow"
    nodes: list[Node] = Field(default_factory=list)
    edges: list[tuple[str, str]] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    theme: str = "ezo"

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, value: Any) -> str:
        return _short(value, 120)


class SocialSpec(BaseModel):
    headline: str
    subline: str = ""
    brand: str = ""
    format: SocialFormat = "square"
    image_prompt: str = ""
    theme: str = "ezo"

    @field_validator("headline", mode="before")
    @classmethod
    def _headline(cls, value: Any) -> str:
        return _short(value, 90)

    @field_validator("subline", mode="before")
    @classmethod
    def _subline(cls, value: Any) -> str:
        return _short(value, 160)

    @field_validator("brand", mode="before")
    @classmethod
    def _brand(cls, value: Any) -> str:
        return _short(value, 40)

    @field_validator("image_prompt", mode="before")
    @classmethod
    def _prompt(cls, value: Any) -> str:
        return _short(value, 1500)


class LogoSpec(BaseModel):
    brand: str
    tagline: str = ""
    symbol_prompt: str = ""
    theme: str = "ezo"

    @field_validator("brand", mode="before")
    @classmethod
    def _brand(cls, value: Any) -> str:
        return _short(value, 40)

    @field_validator("tagline", mode="before")
    @classmethod
    def _tagline(cls, value: Any) -> str:
        return _short(value, 80)

    @field_validator("symbol_prompt", mode="before")
    @classmethod
    def _prompt(cls, value: Any) -> str:
        return _short(value, 1500)


@dataclass(frozen=True, slots=True)
class Composed:
    png: bytes
    width: int
    height: int
    svg: bytes | None = None
    text_fits: bool = True


def _fits(items: list[Primitive]) -> bool:
    return not any(isinstance(i, TextBox) and i.overflow for i in items)


def _render(plan: SlidePlan, width_px: int, *, svg: bool = False) -> Composed:
    png = render_png(plan, width_px)
    height_px = round(plan.height * width_px / plan.width)
    return Composed(png, width_px, height_px, slide_svg(plan) if svg else None, _fits(plan.items))


def compose_diagram(spec: DiagramSpec, language: str) -> Composed:
    """A diagram drawn by EZO's slide engine (exact labels, also exported as SVG)."""
    layout = {"flow": "architecture", "architecture": "architecture"}.get(spec.kind, spec.kind)
    slide = SlideSpec(
        layout=layout,
        title=spec.title,
        nodes=spec.nodes,
        edges=spec.edges,
        steps=spec.steps,
    )
    deck = DeckSpec(
        title=spec.title or "Diagram",
        language=language,
        theme=spec.theme,
        slides=[slide],
    )
    plan = layout_deck(deck, _theme(spec.theme))[0]
    plan.items = [i for i in plan.items if getattr(i, "role", "") != "footer"]
    return _render(plan, 1920, svg=True)


def _abstract(x: float, y: float, w: float, h: float, t: Theme) -> list[Primitive]:
    """An abstract composition used where no generated picture exists."""
    return [
        Rect(x, y, w, h, fill=mix(t.accent2, t.background, 0.82), role="visual"),
        Ellipse(
            x + w * 0.55,
            y - h * 0.15,
            w * 0.7,
            w * 0.7,
            fill=mix(t.accent, t.background, 0.45),
            role="visual",
        ),
        Ellipse(
            x - w * 0.2,
            y + h * 0.35,
            w * 0.55,
            w * 0.55,
            fill=mix(t.accent2, t.background, 0.4),
            role="visual",
        ),
    ]


def compose_social(spec: SocialSpec, image: bytes | None) -> Composed:
    w, h, _, width_px = SOCIAL_FORMATS[spec.format]
    t = _theme(spec.theme)
    band_h = h * (0.46 if spec.format == "story" else 0.4)
    picture_h = h - band_h
    items: list[Primitive] = []
    if image:
        items.append(
            ImageBox(0, 0, w, picture_h, cover_fit(image, w, picture_h), alt=spec.headline)
        )
    else:
        items += _abstract(0, 0, w, picture_h, t)
    items.append(Rect(0, picture_h, w, band_h, fill=t.background, role="background"))
    items.append(Rect(0, picture_h, w * 0.22, 5, fill=t.accent, role="decor"))
    margin = MARGIN * (0.5 if w < 500 else 0.75)
    inner = w - 2 * margin
    y = picture_h + 18
    headline_h = band_h * (0.5 if spec.subline else 0.66)
    items.append(
        text(
            margin,
            y,
            inner,
            headline_h,
            spec.headline,
            34,
            t.ink,
            bold=True,
            min_size=16,
            role="title",
            valign="middle",
        )
    )
    y += headline_h + 4
    if spec.subline:
        items.append(
            text(
                margin,
                y,
                inner,
                band_h * 0.24,
                spec.subline,
                17,
                t.muted,
                min_size=11,
                role="subtitle",
            )
        )
    if spec.brand:
        items.append(
            text(
                margin,
                h - 26,
                inner,
                16,
                spec.brand.upper(),
                11,
                t.accent,
                bold=True,
                min_size=9,
                role="caption",
            )
        )
    plan = SlidePlan(1, "social", spec.headline, w, h, t.background, items)
    return _render(plan, width_px)


def _initials(brand: str) -> str:
    words = [w for w in brand.split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or brand[:1].upper() or "E"


def compose_logo(spec: LogoSpec, symbol: bytes | None) -> Composed:
    """A logo concept sheet: symbol (generated, or a typographic monogram) + wordmark."""
    size = LOGO_SIZE
    t = _theme(spec.theme)
    items: list[Primitive] = []
    box = 220.0
    x, y = (size - box) / 2, 64.0
    if symbol:
        items.append(ImageBox(x, y, box, box, cover_fit(symbol, box, box), alt=spec.brand))
    else:
        items.append(Ellipse(x, y, box, box, fill=t.accent, role="visual"))
        items.append(
            text(
                x,
                y,
                box,
                box,
                _initials(spec.brand),
                96,
                readable_on(t.accent),
                bold=True,
                align="center",
                valign="middle",
                min_size=40,
                role="title",
            )
        )
    items.append(
        text(
            MARGIN,
            318,
            size - 2 * MARGIN,
            70,
            spec.brand,
            46,
            t.ink,
            bold=True,
            align="center",
            valign="middle",
            min_size=22,
            role="title",
        )
    )
    if spec.tagline:
        items.append(
            text(
                MARGIN,
                392,
                size - 2 * MARGIN,
                44,
                spec.tagline,
                18,
                t.muted,
                align="center",
                min_size=11,
                role="subtitle",
            )
        )
    plan = SlidePlan(1, "logo", spec.brand, size, size, t.background, items)
    return _render(plan, 1024)
