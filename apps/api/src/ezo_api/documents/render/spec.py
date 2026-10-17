"""What a presentation contains, independent of how it is drawn.

The PresentationAgent asks a model for this structure as JSON; Pydantic validates
and normalises it (unknown layouts fall back, numbers are checked, text is
trimmed) before any rendering happens.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

LAYOUTS = (
    "cover",
    "title_subtitle",
    "section",
    "hero_image",
    "big_number",
    "kpi",
    "quote",
    "two_column",
    "three_column",
    "comparison",
    "before_after",
    "timeline",
    "process",
    "roadmap",
    "architecture",
    "chart",
    "table",
    "problem_solution",
    "market",
    "product",
    "team",
    "financial",
    "closing",
    "bullets",
)
Layout = Literal[
    "cover",
    "title_subtitle",
    "section",
    "hero_image",
    "big_number",
    "kpi",
    "quote",
    "two_column",
    "three_column",
    "comparison",
    "before_after",
    "timeline",
    "process",
    "roadmap",
    "architecture",
    "chart",
    "table",
    "problem_solution",
    "market",
    "product",
    "team",
    "financial",
    "closing",
    "bullets",
]
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def _clean(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


class Metric(BaseModel):
    value: str = Field(default="", max_length=40)
    label: str = Field(default="", max_length=120)

    @field_validator("value", "label", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return _clean(value, 120)


class Column(BaseModel):
    title: str = ""
    bullets: list[str] = Field(default_factory=list)

    @field_validator("bullets", mode="before")
    @classmethod
    def _bullets(cls, value: Any) -> list[str]:
        return [_clean(v, 200) for v in (value or []) if _clean(v, 200)][:6]


class Step(BaseModel):
    label: str = ""
    text: str = ""

    @field_validator("label", "text", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return _clean(value, 200)


class Series(BaseModel):
    name: str = ""
    values: list[float] = Field(default_factory=list)

    @field_validator("values", mode="before")
    @classmethod
    def _numbers(cls, value: Any) -> list[float]:
        numbers = []
        for item in value or []:
            if isinstance(item, int | float) and not isinstance(item, bool):
                numbers.append(float(item))
            else:
                match = _NUMBER.search(str(item).replace(" ", ""))
                numbers.append(float(match.group(0).replace(",", ".")) if match else float("nan"))
        return numbers


class ChartSpec(BaseModel):
    type: Literal["column", "bar", "line", "pie", "doughnut"] = "column"
    categories: list[str] = Field(default_factory=list)
    series: list[Series] = Field(default_factory=list)
    unit: str = Field(default="", max_length=20)
    source: str = Field(default="", max_length=200)

    @field_validator("categories", mode="before")
    @classmethod
    def _categories(cls, value: Any) -> list[str]:
        return [_clean(v, 40) for v in (value or [])][:24]


class TableSpec(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

    @field_validator("headers", mode="before")
    @classmethod
    def _headers(cls, value: Any) -> list[str]:
        return [_clean(v, 60) for v in (value or [])][:7]

    @field_validator("rows", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> list[list[str]]:
        return [
            [_clean(c, 120) for c in row][:7] for row in (value or []) if isinstance(row, list)
        ][:12]


class Node(BaseModel):
    id: str
    label: str = ""

    @field_validator("label", mode="before")
    @classmethod
    def _label(cls, value: Any) -> str:
        return _clean(value, 60)


class SlideSpec(BaseModel):
    layout: Layout = "bullets"
    title: str = ""
    subtitle: str = ""
    kicker: str = ""
    body: str = ""
    bullets: list[str] = Field(default_factory=list)
    metric: Metric | None = None
    metrics: list[Metric] = Field(default_factory=list)
    quote: str = ""
    author: str = ""
    columns: list[Column] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    chart: ChartSpec | None = None
    table: TableSpec | None = None
    nodes: list[Node] = Field(default_factory=list)
    edges: list[tuple[str, str]] = Field(default_factory=list)
    image_prompt: str = ""
    visual_direction: str = ""
    speaker_notes: str = ""
    sources: list[int] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _layout(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("layout") not in LAYOUTS:
            data = {**data, "layout": "bullets"}
        return data

    @field_validator("title", "subtitle", "kicker", "author", mode="before")
    @classmethod
    def _short(cls, value: Any) -> str:
        return _clean(value, 160)

    @field_validator("body", "quote", "image_prompt", "visual_direction", mode="before")
    @classmethod
    def _long(cls, value: Any) -> str:
        return _clean(value, 600)

    @field_validator("speaker_notes", mode="before")
    @classmethod
    def _notes(cls, value: Any) -> str:
        return str(value or "").strip()[:4000]

    @field_validator("bullets", mode="before")
    @classmethod
    def _bullets(cls, value: Any) -> list[str]:
        return [_clean(v, 220) for v in (value or []) if _clean(v, 220)][:8]

    @field_validator("metrics", mode="before")
    @classmethod
    def _metrics(cls, value: Any) -> list[Any]:
        return list(value or [])[:4]

    @field_validator("steps", mode="before")
    @classmethod
    def _steps(cls, value: Any) -> list[Any]:
        return list(value or [])[:6]

    @field_validator("columns", mode="before")
    @classmethod
    def _columns(cls, value: Any) -> list[Any]:
        return list(value or [])[:3]

    @field_validator("nodes", mode="before")
    @classmethod
    def _nodes(cls, value: Any) -> list[Any]:
        return list(value or [])[:8]

    @field_validator("edges", mode="before")
    @classmethod
    def _edges(cls, value: Any) -> list[tuple[str, str]]:
        edges = []
        for item in value or []:
            if isinstance(item, list | tuple) and len(item) == 2:
                edges.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict) and "from" in item and "to" in item:
                edges.append((str(item["from"]), str(item["to"])))
        return edges[:12]

    @field_validator("sources", mode="before")
    @classmethod
    def _sources(cls, value: Any) -> list[int]:
        return [int(v) for v in (value or []) if str(v).isdigit()][:6]


class DeckSpec(BaseModel):
    title: str
    subtitle: str = ""
    author: str = ""
    language: Literal["uz", "en", "ru"] = "uz"
    theme: str = "ezo"
    aspect_ratio: Literal["16:9", "4:3"] = "16:9"
    audience: str = ""
    goal: str = ""
    slides: list[SlideSpec] = Field(min_length=1, max_length=60)

    @field_validator("title", "subtitle", "author", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return _clean(value, 160)
