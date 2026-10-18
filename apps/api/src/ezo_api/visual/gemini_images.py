"""Google Gemini image generation and editing (official `google-genai` SDK).

Uses a Gemini image model through `generate_content` with image output; editing
sends the original image together with the instruction.
"""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from ezo_api.visual.base import (
    GeneratedImage,
    ImageEditProvider,
    ImageError,
    ImageProvider,
    ImageRequest,
)

_BLOCKED = ("SAFETY", "PROHIBITED", "BLOCKLIST", "IMAGE_SAFETY", "RECITATION")


def _api_error(exc: genai_errors.APIError) -> ImageError:
    status = exc.code if isinstance(exc.code, int) else 0
    if status in (401, 403):
        return ImageError("auth", "The Gemini key was rejected for image generation.")
    if status == 429:
        return ImageError("rate_limit", "The image service is rate limited or out of quota.")
    if status in (400, 404, 422):
        return ImageError("bad_input", "The image service rejected the request.")
    return ImageError("failed", f"The image service failed (HTTP {status or 'error'}).")


class GeminiImageProvider(ImageProvider, ImageEditProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float, client: Any | None = None) -> None:
        self.model = model
        self._client: Any = client or genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=int(timeout * 1000)),
        )

    async def _call(self, contents: list[Any], request: ImageRequest) -> GeneratedImage:
        config = genai_types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=genai_types.ImageConfig(aspect_ratio=request.aspect_ratio),
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except genai_errors.APIError as exc:
            raise _api_error(exc) from exc
        except TimeoutError as exc:
            raise ImageError("timeout", "The image service did not answer in time.") from exc
        except OSError as exc:
            raise ImageError("unavailable", "The image service could not be reached.") from exc

        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise ImageError("refused", "The image service declined this request.")
        reasons: list[str] = []
        for candidate in getattr(response, "candidates", None) or []:
            reason = getattr(candidate, "finish_reason", None)
            reasons.append(str(getattr(reason, "value", reason) or ""))
            content = getattr(candidate, "content", None)
            for part in (content.parts if content and content.parts else []) or []:
                inline = getattr(part, "inline_data", None)
                if inline is not None and inline.data and not getattr(part, "thought", False):
                    return GeneratedImage(
                        data=bytes(inline.data),
                        mime_type=str(inline.mime_type or "image/png"),
                        provider=self.name,
                        model=self.model,
                    )
        if any(any(word in r.upper() for word in _BLOCKED) for r in reasons):
            raise ImageError("refused", "The image service declined this request.")
        raise ImageError("failed", "The image service returned no image.")

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        return await self._call([request.prompt], request)

    async def edit(self, image: bytes, mime_type: str, request: ImageRequest) -> GeneratedImage:
        part = genai_types.Part.from_bytes(data=image, mime_type=mime_type)
        return await self._call([part, request.prompt], request)
