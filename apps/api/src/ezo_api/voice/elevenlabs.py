"""Bounded ElevenLabs REST adapter; server-only credentials, no SDK dependency.

STT and TTS are separate capabilities. TTS needs an explicitly selected voice.
A language is advertised only after the operator verifies their model supports it.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from ezo_api.voice.base import (
    SpeechAudio,
    SpeechToTextProvider,
    TextToSpeechProvider,
    Transcript,
    VoiceError,
    VoiceErrorKind,
)


class ElevenLabsProvider(SpeechToTextProvider, TextToSpeechProvider):
    name = "elevenlabs"

    def __init__(
        self,
        api_key: str,
        *,
        voice_id: str,
        stt_model: str,
        tts_model: str,
        languages: list[str],
        timeout: float,
        max_audio: int,
        max_text: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        for identifier in (stt_model, tts_model):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier):
                raise ValueError("Invalid ElevenLabs model identifier")
        if voice_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", voice_id):
            raise ValueError("Invalid ElevenLabs voice identifier")
        self._key, self.voice_id = api_key, voice_id
        self.stt_model, self.tts_model, self.languages = stt_model, tts_model, languages
        self.timeout, self.max_audio, self.max_text = timeout, max_audio, max_text
        self.transport = transport

    async def _request(self, path: str, limit: int, **kwargs: Any) -> tuple[bytes, str]:
        try:
            async with asyncio.timeout(self.timeout):
                async with (
                    httpx.AsyncClient(
                        base_url="https://api.elevenlabs.io",
                        headers={"xi-api-key": self._key, "Accept-Encoding": "identity"},
                        timeout=httpx.Timeout(self.timeout, connect=10),
                        follow_redirects=False,
                        transport=self.transport,
                    ) as client,
                    client.stream("POST", path, **kwargs) as response,
                ):
                    if response.status_code != 200:
                        kind: VoiceErrorKind = (
                            "auth"
                            if response.status_code in (401, 403)
                            else "rate_limit"
                            if response.status_code == 429
                            else "unavailable"
                        )
                        raise VoiceError(kind, "ElevenLabs could not complete this request.")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise VoiceError("failed", "ElevenLabs returned unsupported encoding.")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > limit:
                            raise VoiceError("failed", "ElevenLabs response size limit exceeded.")
                        data.extend(chunk)
                    return bytes(data), response.headers.get("content-type", "").split(";")[0]
        except (TimeoutError, httpx.TimeoutException):
            raise VoiceError("timeout", "ElevenLabs deadline exceeded.") from None
        except httpx.HTTPError:
            raise VoiceError("unavailable", "ElevenLabs cannot be reached.") from None

    async def transcribe(
        self, audio: bytes, mime_type: str, filename: str, language: str | None
    ) -> Transcript:
        if not audio or len(audio) > self.max_audio:
            raise VoiceError("bad_audio", "Recording exceeds the configured audio limit.")
        # Filenames come from sniff_audio at the API boundary, not client paths.
        fields = {"model_id": self.stt_model, "tag_audio_events": "false", "diarize": "false"}
        if language:
            fields["language_code"] = {"uz": "uzb", "en": "eng", "ru": "rus"}.get(
                language, language
            )
        data, mime = await self._request(
            "/v1/speech-to-text", 256_000, data=fields, files={"file": ("speech", audio, mime_type)}
        )
        try:
            if mime != "application/json":
                raise ValueError
            result = httpx.Response(200, content=data).json()
            text = result.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError
            detected = result.get("language_code")
            heard = detected if isinstance(detected, str) and detected else language
            return Transcript(text.strip(), heard, self.name)
        except (ValueError, AttributeError):
            raise VoiceError("failed", "ElevenLabs returned an invalid transcript.") from None

    async def synthesize(self, text: str, language: str | None) -> SpeechAudio:
        if not self.voice_id:
            raise VoiceError("unavailable", "ElevenLabs TTS needs a configured voice.")
        if language and language not in self.languages:
            raise VoiceError("unavailable", "This ElevenLabs model language has not been verified.")
        if not text.strip() or len(text) > self.max_text:
            raise VoiceError("bad_audio", "Speech text exceeds the configured limit.")
        data, mime = await self._request(
            "/v1/text-to-speech/" + self.voice_id,
            self.max_audio,
            params={"output_format": "mp3_44100_128"},
            json={"text": text, "model_id": self.tts_model},
        )
        if mime != "audio/mpeg" or not data:
            raise VoiceError("failed", "ElevenLabs returned invalid audio.")
        return SpeechAudio(data, mime, self.name)
