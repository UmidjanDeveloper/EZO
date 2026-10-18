"""Image provider interfaces.

EZO never depends on one image vendor. A provider implements generation
(`ImageProvider`) and/or editing (`ImageEditProvider`); `VisualService` tries
them in the configured order. Exact model IDs come from settings, never from code
that calls a provider.

Every image a provider returns is untrusted bytes: it is re-encoded by
`visual.images.normalize_image` before EZO stores or shows it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

AspectRatio = Literal["1:1", "4:3", "3:4", "16:9", "9:16", "4:5", "3:2", "2:3"]
ASPECT_RATIOS: tuple[AspectRatio, ...] = ("1:1", "4:3", "3:4", "16:9", "9:16", "4:5", "3:2", "2:3")
Quality = Literal["low", "medium", "high"]

ImageErrorKind = Literal[
    "unavailable", "auth", "rate_limit", "refused", "bad_input", "timeout", "failed"
]


class ImageError(Exception):
    """A provider could not produce the image. `message` is safe to show."""

    def __init__(self, kind: ImageErrorKind, message: str) -> None:
        self.kind = kind
        self.message = message
        super().__init__(message)


def aspect_value(aspect: str) -> float:
    width, height = aspect.split(":")
    return float(width) / float(height)


@dataclass(frozen=True, slots=True)
class ImageRequest:
    prompt: str
    aspect_ratio: AspectRatio = "1:1"
    quality: Quality = "medium"


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    data: bytes
    mime_type: str
    provider: str
    model: str
    revised_prompt: str | None = None
    """The provider's own rewrite of the prompt, when it reports one."""


class ImageProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def generate(self, request: ImageRequest) -> GeneratedImage:
        """Create one image from a text prompt. Raises `ImageError`."""


class ImageEditProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def edit(self, image: bytes, mime_type: str, request: ImageRequest) -> GeneratedImage:
        """Change an existing image as the prompt describes. Raises `ImageError`."""
