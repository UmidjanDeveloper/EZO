"""Safe image handling.

Images from providers and uploads are untrusted bytes. Before EZO stores or shows
one, Pillow must open it as a real raster image of reasonable size; it is then
re-encoded, which drops metadata (EXIF, location) and anything appended to the file.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 40_000_000
"""Larger images are refused before decoding (decompression bombs)."""
MAX_SIDE = 2048
ALLOWED_FORMATS = frozenset({"PNG", "JPEG", "WEBP", "GIF"})


class ImageRejectedError(Exception):
    """The bytes are not an acceptable image. `message` is safe to show."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    data: bytes
    width: int
    height: int
    mime_type: str = "image/png"


def open_image(data: bytes) -> Image.Image:
    """Open and fully decode an image, refusing non-images and oversized ones."""
    if not data:
        raise ImageRejectedError("The image is empty.")
    if len(data) > MAX_INPUT_BYTES:
        raise ImageRejectedError("The image file is too large.")
    try:
        probe = Image.open(io.BytesIO(data))
        if probe.format not in ALLOWED_FORMATS:
            raise ImageRejectedError(f"Unsupported image format: {probe.format}.")
        width, height = probe.size
        if width < 1 or height < 1 or width * height > MAX_PIXELS:
            raise ImageRejectedError("The image dimensions are not acceptable.")
        probe.verify()  # structure check; the object cannot be used afterwards
        decoded: Image.Image = Image.open(io.BytesIO(data))
        decoded.load()
    except ImageRejectedError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageRejectedError("The file is not a valid image.") from exc
    image = ImageOps.exif_transpose(decoded)
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    return image.convert("RGBA" if has_alpha else "RGB")


def crop_to_aspect(image: Image.Image, aspect: float) -> Image.Image:
    """Centre crop to width/height = aspect (cover fit)."""
    width, height = image.size
    if abs(width / height - aspect) < 0.01:
        return image
    if width / height > aspect:
        new_w = max(1, round(height * aspect))
        left = (width - new_w) // 2
        return image.crop((left, 0, left + new_w, height))
    new_h = max(1, round(width / aspect))
    top = (height - new_h) // 2
    return image.crop((0, top, width, top + new_h))


def _shrink(image: Image.Image, max_side: int) -> Image.Image:
    if max(image.size) <= max_side:
        return image
    image = image.copy()
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def normalize_image(
    data: bytes, *, aspect: float | None = None, max_side: int = MAX_SIDE
) -> NormalizedImage:
    """A clean PNG of the image, optionally cropped to an aspect ratio."""
    image = open_image(data)
    if aspect:
        image = crop_to_aspect(image, aspect)
    image = _shrink(image, max_side)
    return NormalizedImage(_png(image), image.width, image.height)


def thumbnail(data: bytes, max_side: int = 512) -> bytes:
    return _png(_shrink(open_image(data), max_side))


def cover_fit(data: bytes, width: float, height: float, *, max_px: int = 1600) -> bytes:
    """The image cropped to a box's proportions, as JPEG (for slides and documents)."""
    image = crop_to_aspect(open_image(data), width / height)
    image = _shrink(image, max_px)
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        image = background
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=86, optimize=True)
    return buffer.getvalue()
