"""Ordered image providers with fallback, plus EZO's limits for paid image calls."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from ezo_api.settings import Settings
from ezo_api.visual.base import (
    GeneratedImage,
    ImageEditProvider,
    ImageError,
    ImageProvider,
    ImageRequest,
    aspect_value,
)
from ezo_api.visual.gemini_images import GeminiImageProvider
from ezo_api.visual.images import ImageRejectedError, NormalizedImage, normalize_image
from ezo_api.visual.openai_images import OpenAIImageProvider

logger = logging.getLogger(__name__)
P = TypeVar("P", ImageProvider, ImageEditProvider)


@dataclass(slots=True)
class ImageAttempt:
    provider: str
    model: str
    ok: bool
    kind: str | None = None
    message: str | None = None


class AllImageProvidersFailedError(Exception):
    def __init__(self, attempts: list[ImageAttempt]) -> None:
        self.attempts = attempts
        self.refused = any(a.kind == "refused" for a in attempts)
        last = attempts[-1].message if attempts else None
        self.message = last or "No image provider is configured."
        super().__init__(self.message)


@dataclass(slots=True)
class ImageOutcome:
    image: NormalizedImage
    provider: str
    model: str
    revised_prompt: str | None
    attempts: list[ImageAttempt] = field(default_factory=list)


class VisualService:
    def __init__(
        self,
        generators: Sequence[ImageProvider] = (),
        editors: Sequence[ImageEditProvider] = (),
        *,
        quality: str = "medium",
        max_per_request: int = 4,
        max_per_deck: int = 4,
    ) -> None:
        self.generators = list(generators)
        self.editors = list(editors)
        self.quality = quality if quality in ("low", "medium", "high") else "medium"
        self.max_per_request = max(1, max_per_request)
        self.max_per_deck = max(0, max_per_deck)

    @property
    def can_generate(self) -> bool:
        return bool(self.generators)

    @property
    def can_edit(self) -> bool:
        return bool(self.editors)

    def describe(self) -> list[dict[str, object]]:
        names = {p.name: p.model for p in self.generators}
        edit = {p.name for p in self.editors}
        return [
            {"name": name, "model": model, "edit": name in edit} for name, model in names.items()
        ]

    async def _first_working(
        self,
        providers: Sequence[P],
        call: Callable[[P], Awaitable[GeneratedImage]],
        aspect: str,
    ) -> ImageOutcome:
        attempts: list[ImageAttempt] = []
        for provider in providers:
            try:
                generated = await call(provider)
                image = normalize_image(generated.data, aspect=aspect_value(aspect))
            except ImageError as exc:
                logger.warning("Image provider %s failed: %s", provider.name, exc.kind)
                attempts.append(
                    ImageAttempt(provider.name, provider.model, False, exc.kind, exc.message)
                )
                if exc.kind == "refused":
                    break  # never shop around for a provider that accepts a declined request
                continue
            except ImageRejectedError as exc:
                logger.warning("Image provider %s returned an invalid image", provider.name)
                attempts.append(
                    ImageAttempt(provider.name, provider.model, False, "failed", exc.message)
                )
                continue
            attempts.append(ImageAttempt(provider.name, provider.model, True))
            return ImageOutcome(
                image, generated.provider, generated.model, generated.revised_prompt, attempts
            )
        raise AllImageProvidersFailedError(attempts)

    def request(self, prompt: str, aspect_ratio: str) -> ImageRequest:
        return ImageRequest(
            prompt=prompt[:4000],
            aspect_ratio=aspect_ratio,  # type: ignore[arg-type]
            quality=self.quality,  # type: ignore[arg-type]
        )

    async def generate(self, prompt: str, aspect_ratio: str = "1:1") -> ImageOutcome:
        request = self.request(prompt, aspect_ratio)
        return await self._first_working(
            self.generators, lambda p: p.generate(request), aspect_ratio
        )

    async def edit(
        self, image: bytes, mime_type: str, prompt: str, aspect_ratio: str = "1:1"
    ) -> ImageOutcome:
        request = self.request(prompt, aspect_ratio)
        return await self._first_working(
            self.editors, lambda p: p.edit(image, mime_type, request), aspect_ratio
        )


def build_visual_service(settings: Settings) -> VisualService:
    """Providers in the order of EZO_IMAGE_PROVIDERS ("auto" = OpenAI, then Gemini; "none")."""
    available: dict[str, OpenAIImageProvider | GeminiImageProvider] = {}
    timeout = settings.image_timeout_seconds
    if settings.openai_api_key:
        available["openai"] = OpenAIImageProvider(
            settings.openai_api_key.get_secret_value(),
            settings.openai_image_model,
            timeout,
            settings.openai_base_url,
        )
    if settings.gemini_api_key:
        available["gemini"] = GeminiImageProvider(
            settings.gemini_api_key.get_secret_value(), settings.gemini_image_model, timeout
        )
    order = (
        ["openai", "gemini"] if settings.image_providers == ["auto"] else settings.image_providers
    )
    chosen = [available[name] for name in order if name in available]
    return VisualService(
        chosen,
        chosen,
        quality=settings.image_quality,
        max_per_request=settings.image_max_per_request,
        max_per_deck=settings.image_max_per_deck,
    )
