"""Presentation quality checks (run on the laid-out slides before export)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from ezo_api.documents.render.primitives import (
    ChartBox,
    Ellipse,
    Rect,
    SlidePlan,
    TableBox,
    TextBox,
)
from ezo_api.documents.render.spec import DeckSpec, SlideSpec

Severity = Literal["error", "warning", "info"]
# Smallest acceptable fitted sizes per text role (points).
MIN_SIZE = {
    "title": 20.0,
    "footer": 8.0,
    "caption": 9.0,
    "chart_label": 7.0,
    "table_cell": 8.0,
    "kicker": 9.0,
}
DEFAULT_MIN = 11.0
MAX_WORDS = 80
MAX_BULLETS = 6
DECORATIVE = {"decor", "visual", "background"}


@dataclass(frozen=True, slots=True)
class Issue:
    slide: int
    severity: Severity
    code: str
    message: str


@dataclass(slots=True)
class QAReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "errors": len(self.errors),
            "warnings": len([i for i in self.issues if i.severity == "warning"]),
            "issues": [
                {"slide": i.slide, "severity": i.severity, "code": i.code, "message": i.message}
                for i in self.issues
            ],
        }


def _words(slide: SlideSpec) -> int:
    parts = [slide.title, slide.subtitle, slide.body, slide.quote, *slide.bullets]
    parts += [c.title + " " + " ".join(c.bullets) for c in slide.columns]
    parts += [s.label + " " + s.text for s in slide.steps]
    parts += [m.value + " " + m.label for m in slide.metrics]
    return sum(len(p.split()) for p in parts if p)


def check_chart(chart: ChartBox) -> list[str]:
    problems = []
    if not chart.categories:
        problems.append("the chart has no categories")
    if not chart.series:
        problems.append("the chart has no data series")
    for name, values in chart.series:
        if len(values) != len(chart.categories):
            problems.append(
                f"series “{name}” has {len(values)} values for {len(chart.categories)} categories"
            )
        if any(math.isnan(v) for v in values):
            problems.append(f"series “{name}” contains values that are not numbers")
        if chart.kind in ("pie", "doughnut") and any(v < 0 for v in values if not math.isnan(v)):
            problems.append("a pie chart cannot show negative values")
    return problems


def run_qa(deck: DeckSpec, plans: list[SlidePlan]) -> QAReport:
    report = QAReport()
    add = report.issues.append
    titles: dict[str, int] = {}
    for slide, plan in zip(deck.slides, plans, strict=True):
        n = plan.index
        texts = [i for i in plan.items if isinstance(i, TextBox)]
        content = [
            t
            for t in texts
            if t.role not in ("footer",) and any(p.text.strip() for p in t.paragraphs)
        ]
        if not content and not any(isinstance(i, ChartBox | TableBox) for i in plan.items):
            add(Issue(n, "error", "empty_slide", "The slide has no content."))
        for box in texts:
            if box.overflow:
                add(
                    Issue(
                        n,
                        "error",
                        "text_overflow",
                        f"Text in “{box.role}” does not fit even at {box.fitted_size:g} pt.",
                    )
                )
            minimum = MIN_SIZE.get(box.role, DEFAULT_MIN)
            if box.fitted_size and box.fitted_size < minimum:
                add(
                    Issue(
                        n,
                        "error",
                        "font_too_small",
                        f"“{box.role}” text is {box.fitted_size:g} pt (minimum {minimum:g} pt).",
                    )
                )
        for item in plan.items:
            role = getattr(item, "role", "")
            if role in DECORATIVE or (isinstance(item, Ellipse) and role == "decor"):
                continue
            if isinstance(item, Rect | TextBox | ChartBox | TableBox | Ellipse) and (
                item.x < -0.5
                or item.y < -0.5
                or item.x + item.w > plan.width + 0.5
                or item.y + item.h > plan.height + 0.5
            ):
                add(
                    Issue(
                        n,
                        "error",
                        "out_of_bounds",
                        f"An element ({role or type(item).__name__}) extends beyond the slide.",
                    )
                )
            if isinstance(item, ChartBox):
                for problem in check_chart(item):
                    add(Issue(n, "error", "chart_data", problem[0].upper() + problem[1:] + "."))
        if slide.layout in ("chart", "financial") and slide.chart is None and slide.table is None:
            add(Issue(n, "error", "chart_missing", "A chart slide has no chart data."))
        if slide.layout == "table" and (slide.table is None or not slide.table.headers):
            add(Issue(n, "error", "table_missing", "A table slide has no table."))
        title_only_ok = ("cover", "title_subtitle", "section", "closing", "quote", "big_number")
        has_data = any(isinstance(i, ChartBox | TableBox) for i in plan.items)
        only_title = bool(content) and all(t.role in ("title", "kicker") for t in content)
        if only_title and slide.layout not in title_only_ok and not has_data:
            add(Issue(n, "warning", "title_only", "The slide has a title but no content."))
        words = _words(slide)
        if words > MAX_WORDS:
            add(
                Issue(
                    n,
                    "warning",
                    "dense_slide",
                    f"{words} words on one slide; consider splitting it.",
                )
            )
        if len(slide.bullets) > MAX_BULLETS:
            add(
                Issue(
                    n,
                    "warning",
                    "too_many_bullets",
                    f"{len(slide.bullets)} bullet points (recommended ≤ {MAX_BULLETS}).",
                )
            )
        key = slide.title.strip().lower()
        if key and slide.layout not in ("section", "closing"):
            if key in titles:
                add(Issue(n, "warning", "duplicate_title", f"Same title as slide {titles[key]}."))
            titles.setdefault(key, n)
        if slide.image_prompt:
            add(
                Issue(
                    n,
                    "info",
                    "image_pending",
                    "An image was planned; image generation is not available yet "
                    "(an abstract visual is used).",
                )
            )
    return report
