"""Speech and transcription via ElevenLabs API.

Provides state-of-the-art multilingual voice synthesis with high-fidelity
Uzbek and multi-language support, plus speech-to-text with graceful fallback.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ezo_api.voice.base import (
    SpeechAudio,
    SpeechToTextProvider,
    TextToSpeechProvider,
    Transcript,
    VoiceError,
)

logger = logging.getLogger(__name__)

MAX_TTS_CHARS = 4000
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


def _map_http_error(exc: Exception, provider: str) -> VoiceError:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return VoiceError("auth", f"{provider}: the API key was rejected.")
        if code == 429:
            return VoiceError("rate_limit", f"{provider}: quota exceeded or rate limit hit.")
        if code == 400:
            return VoiceError(
                "bad_audio", f"{provider}: the request or audio could not be processed."
            )
        if code >= 500:
            return VoiceError("unavailable", f"{provider}: ElevenLabs service error ({code}).")
        return VoiceError("failed", f"{provider}: HTTP {code}.")
    if isinstance(exc, httpx.TimeoutException):
        return VoiceError("timeout", f"{provider}: request timed out.")
    if isinstance(exc, httpx.NetworkError):
        return VoiceError("unavailable", f"{provider}: cannot reach ElevenLabs API.")
    return VoiceError("failed", f"{provider}: {type(exc).__name__}.")


class ElevenLabsAudioProvider(SpeechToTextProvider, TextToSpeechProvider):
    def __init__(
        self,
        name: str = "elevenlabs",
        *,
        api_key: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str = "eleven_multilingual_v2",
        stt_model: str = "scribe_v1",
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.stt_model = stt_model
        self.timeout = timeout
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=self.timeout)

    async def synthesize(self, text: str, language: str | None) -> SpeechAudio:
        """Synthesize speech using ElevenLabs Text-to-Speech."""
        if not text.strip():
            raise VoiceError("bad_audio", f"{self.name}: empty text supplied for synthesis.")

        url = f"{ELEVENLABS_API_BASE}/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload: dict[str, Any] = {
            "text": text[:MAX_TTS_CHARS],
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        # Include language hint if model supports it
        if language:
            payload["language_code"] = language

        client = self._get_client()
        try:
            should_close = self._client is None
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.content
            finally:
                if should_close:
                    await client.aclose()
        except Exception as exc:
            raise _map_http_error(exc, self.name) from exc

        if not data:
            raise VoiceError("failed", f"{self.name}: returned no audio content.")

        return SpeechAudio(data=data, mime_type="audio/mpeg", provider=self.name)

    async def transcribe(
        self, audio: bytes, mime_type: str, filename: str, language: str | None
    ) -> Transcript:
        """Transcribe speech using ElevenLabs Speech-to-Text."""
        if not audio:
            raise VoiceError("bad_audio", f"{self.name}: empty audio bytes supplied.")

        url = f"{ELEVENLABS_API_BASE}/speech-to-text"
        headers = {
            "xi-api-key": self.api_key,
        }
        files = {
            "file": (filename or "audio.wav", audio, mime_type or "audio/wav"),
        }
        data: dict[str, Any] = {
            "model_id": self.stt_model,
        }
        if language:
            data["language_code"] = language

        client = self._get_client()
        try:
            should_close = self._client is None
            try:
                response = await client.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
            finally:
                if should_close:
                    await client.aclose()
        except Exception as exc:
            raise _map_http_error(exc, self.name) from exc

        text = str(result.get("text", "")).strip()
        detected_lang = result.get("language_code") or language
        return Transcript(text=text, language=detected_lang, provider=self.name)
