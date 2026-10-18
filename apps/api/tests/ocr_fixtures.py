"""Page images with known text, rendered with the bundled Liberation Sans font
(Latin + Cyrillic), for real OCR tests."""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = Path(__file__).parents[1] / "src/ezo_api/documents/fonts/LiberationSans-Regular.ttf"

UZ_LATIN = [
    "O'zbekiston Respublikasi Prezidentining qarori",
    "Ta'lim tizimini rivojlantirish to'g'risida",
    "Ushbu qaror 2026-yil 1-yanvardan kuchga kiradi.",
]
UZ_CYRILLIC = [
    "Ўзбекистон Республикаси Президентининг қарори",
    "Таълим тизимини ривожлантириш тўғрисида",
    "Ушбу қарор 2026 йил 1 январдан кучга киради.",
]
RUSSIAN = [
    "Постановление Президента Республики Узбекистан",
    "О развитии системы образования",
    "Настоящее постановление вступает в силу.",
]
ENGLISH = [
    "The quick brown fox jumps over the lazy dog.",
    "Payment is due by the fifth of each month.",
]

REQUIRED = bool(os.environ.get("EZO_REQUIRE_TESSERACT"))
"""Set in CI: missing Tesseract then fails the OCR tests instead of skipping them."""

needs_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None and not REQUIRED, reason="Tesseract OCR is not installed"
)


def page_image(
    lines: list[str], *, rotate: int = 0, skew: float = 0.0, blur: float = 0.0, size: int = 40
) -> Image.Image:
    """`rotate` turns the page counter-clockwise (as a sideways scan); `skew` likewise."""
    font = ImageFont.truetype(str(FONT), size)
    image = Image.new("L", (1600, 140 + 70 * len(lines)), 255)
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((80, 60 + 70 * index), line, font=font, fill=0)
    if skew:
        image = image.rotate(skew, expand=True, fillcolor=255)
    if rotate:
        image = image.rotate(rotate, expand=True, fillcolor=255)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    return image


def png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def words(text: str) -> set[str]:
    return {w.strip(".,").lower() for w in text.split() if w.strip(".,")}


def recall(expected: list[str], text: str) -> float:
    """Share of expected words that OCR read exactly."""
    wanted = words(" ".join(expected))
    return len(wanted & words(text)) / len(wanted)
