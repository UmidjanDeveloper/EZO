"""Speech through the OpenAI audio API — and any server that speaks the same protocol.

Used for two providers:

- **OpenAI** (`OPENAI_API_KEY`): `gpt-4o-mini-transcribe` / `gpt-4o-mini-tts` by default.
- **VoiceStudio** (`VOICESTUDIO_URL`): a separately run, optional service that offers an
  OpenAI-compatible `/v1/audio/*` API. EZO only talks to it over HTTP; no VoiceStudio code
  is part of EZO (see docs/OPEN_SOURCE_AUDIT.md).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx2 as httpx
import openai

from ezo_api.voice.base import (
    SpeechAudio,
    SpeechToTextProvider,
    TextToSpeechProvider,
    Transcript,
    VoiceError,
)
from ezo_api.voice.http_limits import BoundedAudioClient

MAX_TTS_CHARS = 4000


def _voice_error(exc: Exception, provider: str) -> VoiceError:
    if isinstance(exc, VoiceError):
        return exc
    if isinstance(exc, TimeoutError):
        return VoiceError("timeout", f"{provider}: the voice deadline expired.")
    if isinstance(exc, openai.APIConnectionError) and isinstance(exc.__cause__, VoiceError):
        return exc.__cause__
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return VoiceError("auth", f"{provider}: the API key was rejected.")
    if isinstance(exc, openai.RateLimitError):
        return VoiceError("rate_limit", f"{provider}: too many requests or quota exceeded.")
    if isinstance(exc, openai.APITimeoutError):
        return VoiceError("timeout", f"{provider}: the voice service took too long.")
    if isinstance(exc, openai.APIConnectionError):
        return VoiceError("unavailable", f"{provider}: the voice service cannot be reached.")
    if isinstance(exc, openai.BadRequestError):
        return VoiceError("bad_audio", f"{provider}: the audio could not be processed.")
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return VoiceError("unavailable", f"{provider}: the voice service had an error.")
    return VoiceError("failed", f"{provider}: {type(exc).__name__}.")


class OpenAIAudioProvider(SpeechToTextProvider, TextToSpeechProvider):
    def __init__(
        self,
        name: str,
        *,
        api_key: str,
        base_url: str | None = None,
        stt_model: str,
        tts_model: str,
        voice: str,
        send_language_to_tts: bool = False,
        timeout: float = 60.0,
        client: Any = None,
        max_audio: int = 10 * 1024 * 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not 1 <= max_audio <= 25 * 1024 * 1024 or not 0 < timeout <= 300:
            raise ValueError("Invalid voice resource limits")
        self.timeout, self.max_audio = timeout, max_audio
        self.name = name
        self.stt_model = stt_model
        self.tts_model = tts_model
        self.voice = voice
        # VoiceStudio accepts a `language` field on /v1/audio/speech; OpenAI does not.
        self.send_language_to_tts = send_language_to_tts
        self._client: Any = client or openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=1,
            http_client=BoundedAudioClient(
                max_audio=max_audio, timeout=timeout, transport=transport
            ),
        )

    async def transcribe(
        self, audio: bytes, mime_type: str, filename: str, language: str | None
    ) -> Transcript:
        if not audio or len(audio) > self.max_audio:
            raise VoiceError("bad_audio", "Recording exceeds the configured audio limit.")
        try:
            async with asyncio.timeout(self.timeout):
                result = await self._client.audio.transcriptions.create(
                    model=self.stt_model,
                    file=(filename, audio, mime_type),
                    **({"language": language} if language else {}),
                )
        except Exception as exc:
            raise _voice_error(exc, self.name) from exc
        text = str(getattr(result, "text", "") or "").strip()
        detected = getattr(result, "language", None)
        return Transcript(text=text, language=detected or language, provider=self.name)

    async def synthesize(self, text: str, language: str | None) -> SpeechAudio:
        extra = {"language": language} if (self.send_language_to_tts and language) else None
        try:
            async with asyncio.timeout(self.timeout):
                response = await self._client.audio.speech.create(
                    model=self.tts_model,
                    voice=self.voice,
                    input=text[:MAX_TTS_CHARS],
                    response_format="mp3",
                    **({"extra_body": extra} if extra else {}),
                )
                data = response.content if hasattr(response, "content") else await response.aread()
        except Exception as exc:
            raise _voice_error(exc, self.name) from exc
        if len(data) > self.max_audio:
            raise VoiceError("failed", "Voice response size limit exceeded.")
        if not data:
            raise VoiceError("failed", f"{self.name}: returned no audio.")
        return SpeechAudio(data=bytes(data), mime_type="audio/mpeg", provider=self.name)
