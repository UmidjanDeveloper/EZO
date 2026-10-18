"""Page image preparation before OCR: grayscale, contrast, upscaling of small images,
rotation (from Tesseract's orientation detection) and deskew (projection profile)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

MIN_WIDTH = 1_400
"""Narrower page images are upscaled: Tesseract reads text best at ~25-35 px x-height."""
MAX_SIDE = 7_000
MAX_SKEW = 5.0
SKEW_STEP = 0.25


@dataclass(slots=True)
class Prepared:
    image: Image.Image
    steps: list[str] = field(default_factory=list)
    deskew_angle: float = 0.0


def prepare(image: Image.Image) -> Prepared:
    steps: list[str] = []
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, "white")
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    gray = ImageOps.grayscale(image)
    steps.append("grayscale")
    gray = ImageOps.autocontrast(gray, cutoff=1)
    steps.append("autocontrast")
    if gray.width < MIN_WIDTH:
        scale = min(MIN_WIDTH / gray.width, 4.0)
        size = (round(gray.width * scale), round(gray.height * scale))
        if max(size) <= MAX_SIDE:
            gray = gray.resize(size, Image.Resampling.LANCZOS)
            steps.append(f"upscale x{scale:.1f}")
    angle = estimate_skew(gray)
    if abs(angle) >= 0.3:
        gray = gray.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
        steps.append(f"deskew {angle:+.2f}°")
    return Prepared(gray, steps, angle)


def rotate_clockwise(image: Image.Image, degrees: int) -> Image.Image:
    if degrees % 360 == 0:
        return image
    return image.rotate(-degrees, expand=True, fillcolor=255 if image.mode == "L" else "white")


def estimate_skew(gray: Image.Image) -> float:
    """Angle (degrees, counter-clockwise) that makes text lines horizontal: the rotation
    whose row-ink profile has the sharpest peaks. Returns 0 for blank pages."""
    small = gray.copy()
    small.thumbnail((900, 900))
    ink = np.asarray(small, dtype=np.uint8) < 128
    if ink.mean() < 0.002:
        return 0.0
    mask = Image.fromarray((ink * 255).astype(np.uint8))
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-MAX_SKEW, MAX_SKEW + SKEW_STEP / 2, SKEW_STEP):
        rotated = np.asarray(mask.rotate(float(angle), expand=False), dtype=np.float64)
        profile = rotated.sum(axis=1)
        score = float(np.square(np.diff(profile)).sum())
        if score > best_score:
            best_angle, best_score = float(angle), score
    return round(best_angle, 2)
