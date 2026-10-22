"""Bound response bytes before SDK buffering, preserving HTTPX proxy/TLS defaults."""

from collections.abc import AsyncIterator
from typing import Any

import httpx2 as httpx

from ezo_api.voice.base import VoiceError


class LimitedStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, limit: int) -> None:
        self.stream, self.limit = stream, limit

    async def __aiter__(self) -> AsyncIterator[bytes]:
        count = 0
        async for chunk in self.stream:
            count += len(chunk)
            if count > self.limit:
                raise VoiceError("failed", "Voice response size limit exceeded.")
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


class BoundedAudioClient(httpx.AsyncClient):
    def __init__(self, *, max_audio: int, timeout: float, **kwargs: Any) -> None:
        self.max_audio = max_audio
        super().__init__(
            headers={"Accept-Encoding": "identity"},
            timeout=timeout,
            follow_redirects=False,
            **kwargs,
        )

    async def send(
        self, request: httpx.Request, *, stream: bool = False, **kwargs: Any
    ) -> httpx.Response:
        response = await super().send(request, stream=True, **kwargs)
        try:
            if 300 <= response.status_code < 400:
                raise VoiceError("unavailable", "Voice redirects are not supported.")
            if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
                raise VoiceError("failed", "Voice response encoding is not supported.")
            limit = self.max_audio if request.url.path.endswith("/audio/speech") else 256_000
            if response.is_error:
                limit = min(limit, 256_000)
            length = response.headers.get("content-length")
            if length is not None:
                if not length.isascii() or not length.isdigit() or len(length) > 20:
                    raise VoiceError("failed", "Invalid voice response length.")
                if int(length) > limit:
                    raise VoiceError("failed", "Voice response size limit exceeded.")
            if not isinstance(response.stream, httpx.AsyncByteStream):
                raise VoiceError("failed", "Unsupported voice response stream.")
            response.stream = LimitedStream(response.stream, limit)
            if not stream:
                await response.aread()
            return response
        except BaseException:
            await response.aclose()
            raise
