"""OpenAI image generation and editing (official `openai` SDK, Images API)."""

from __future__ import annotations

import base64
from typing import Any

import openai

from ezo_api.visual.base import (
    GeneratedImage,
    ImageEditProvider,
    ImageError,
    ImageProvider,
    ImageRequest,
    aspect_value,
)

_REFUSAL_CODES = frozenset({"moderation_blocked", "content_policy_violation", "safety_violation"})


def size_for(aspect: str) -> str:
    """The closest size GPT image models accept; EZO crops to the exact ratio afterwards."""
    value = aspect_value(aspect)
    if value >= 1.2:
        return "1536x1024"
    if value <= 0.83:
        return "1024x1536"
    return "1024x1024"


def _error(exc: Exception) -> ImageError:
    if isinstance(exc, openai.APITimeoutError):
        return ImageError("timeout", "The image service did not answer in time.")
    if isinstance(exc, openai.APIConnectionError):
        return ImageError("unavailable", "The image service could not be reached.")
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return ImageError("auth", "The OpenAI key was rejected for image generation.")
    if isinstance(exc, openai.RateLimitError):
        return ImageError("rate_limit", "The image service is rate limited or out of credit.")
    if isinstance(exc, openai.BadRequestError):
        code = str(getattr(exc, "code", "") or "")
        if code in _REFUSAL_CODES or "safety" in exc.message.lower():
            return ImageError("refused", "The image service declined this request.")
        return ImageError("bad_input", "The image service rejected the request.")
    if isinstance(exc, openai.APIStatusError):
        return ImageError("failed", f"The image service failed (HTTP {exc.status_code}).")
    return ImageError("failed", "The image service failed.")


class OpenAIImageProvider(ImageProvider, ImageEditProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self._client: Any = client or openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1
        )

    def _result(self, response: Any) -> GeneratedImage:
        items = getattr(response, "data", None) or []
        encoded = getattr(items[0], "b64_json", None) if items else None
        if not encoded:
            raise ImageError("failed", "The image service returned no image.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ImageError("failed", "The image service returned unreadable data.") from exc
        revised = getattr(items[0], "revised_prompt", None)
        return GeneratedImage(
            data=data,
            mime_type="image/png",
            provider=self.name,
            model=self.model,
            revised_prompt=str(revised) if revised else None,
        )

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        try:
            response = await self._client.images.generate(
                model=self.model,
                prompt=request.prompt,
                size=size_for(request.aspect_ratio),
                quality=request.quality,
                n=1,
            )
        except openai.OpenAIError as exc:
            raise _error(exc) from exc
        return self._result(response)

    async def edit(self, image: bytes, mime_type: str, request: ImageRequest) -> GeneratedImage:
        extension = "jpg" if mime_type == "image/jpeg" else "png"
        try:
            response = await self._client.images.edit(
                model=self.model,
                image=(f"image.{extension}", image, mime_type),
                prompt=request.prompt,
                size=size_for(request.aspect_ratio),
                quality=request.quality,
                n=1,
            )
        except openai.OpenAIError as exc:
            raise _error(exc) from exc
        return self._result(response)
