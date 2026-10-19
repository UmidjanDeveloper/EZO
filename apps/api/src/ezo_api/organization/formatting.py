"""Standard document formatting of an organization (font, size, margins, spacing)."""

from __future__ import annotations

from typing import Any

from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from pydantic import BaseModel, Field


class Margins(BaseModel):
    top: float = Field(default=2.0, ge=0.5, le=5.0)
    bottom: float = Field(default=2.0, ge=0.5, le=5.0)
    left: float = Field(default=3.0, ge=0.5, le=5.0)
    right: float = Field(default=1.5, ge=0.5, le=5.0)


class Formatting(BaseModel):
    """Defaults follow common Uzbek office practice (Times New Roman 14, 30/15/20/20 mm)."""

    font_name: str = Field(default="Times New Roman", min_length=1, max_length=60)
    font_size: float = Field(default=14, ge=8, le=20)
    line_spacing: float = Field(default=1.15, ge=1.0, le=3.0)
    indent_cm: float = Field(default=1.25, ge=0.0, le=3.0)
    margins_cm: Margins = Field(default_factory=Margins)


def formatting_of(data: dict[str, Any] | None) -> Formatting:
    try:
        return Formatting.model_validate(data or {})
    except ValueError:
        return Formatting()


def apply(document: object, fmt: Formatting, *, small: bool = False) -> None:
    """Set the Normal style and the page margins of a python-docx Document."""
    normal = document.styles["Normal"]  # type: ignore[attr-defined]
    normal.font.name = fmt.font_name
    normal.font.size = Pt(max(8, fmt.font_size - 2) if small else fmt.font_size)
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), fmt.font_name)
    normal.paragraph_format.line_spacing = fmt.line_spacing
    for section in document.sections:  # type: ignore[attr-defined]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.top_margin = Cm(fmt.margins_cm.top)
        section.bottom_margin = Cm(fmt.margins_cm.bottom)
        section.left_margin = Cm(fmt.margins_cm.left)
        section.right_margin = Cm(fmt.margins_cm.right)
