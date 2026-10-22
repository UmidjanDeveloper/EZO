"""Ordered voice providers with fallback."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from ezo_api.settings import Settings
from ezo_api.voice.base import (
    SpeechAudio,
    SpeechToTextProvider,
    TextToSpeechProvider,
    Transcript,
    VoiceError,
)
from ezo_api.voice.elevenlabs_audio import ElevenLabsAudioProvider
from ezo_api.voice.openai_audio import OpenAIAudioProvider

logger = logging.getLogger(__name__)
T = TypeVar("T")
P = TypeVar("P", SpeechToTextProvider, TextToSpeechProvider)
AudioProvider = SpeechToTextProvider | TextToSpeechProvider


@dataclass(slots=True)
class VoiceAttempt:
    provider: str
    ok: bool
    kind: str | None = None
    message: str | None = None


class AllVoiceProvidersFailedError(Exception):
    def __init__(self, attempts: list[VoiceAttempt]) -> None:
        self.attempts = attempts
        super().__init__("; ".join(a.message or a.provider for a in attempts))


@dataclass(slots=True)
class VoiceResult[T]:
    value: T
    attempts: list[VoiceAttempt] = field(default_factory=list)


class VoiceService:
    def __init__(
        self,
        stt: Sequence[SpeechToTextProvider] = (),
        tts: Sequence[TextToSpeechProvider] = (),
    ) -> None:
        self.stt = list(stt)
        self.tts = list(tts)

    async def _first_working(
        self, providers: Sequence[P], call: Callable[[P], Awaitable[T]]
    ) -> VoiceResult[T]:
        attempts: list[VoiceAttempt] = []
        for provider in providers:
            try:
                value = await call(provider)
            except VoiceError as exc:
                logger.warning("Voice provider %s failed: %s", provider.name, exc.kind)
                attempts.append(VoiceAttempt(provider.name, False, exc.kind, exc.message))
                if exc.kind == "bad_audio":
                    break  # the recording itself is the problem; another provider won't help
                continue
            attempts.append(VoiceAttempt(provider.name, True))
            return VoiceResult(value, attempts)
        raise AllVoiceProvidersFailedError(attempts)

    async def transcribe(
        self, audio: bytes, mime_type: str, filename: str, language: str | None
    ) -> VoiceResult[Transcript]:
        return await self._first_working(
            self.stt, lambda p: p.transcribe(audio, mime_type, filename, language)
        )

    async def synthesize(self, text: str, language: str | None) -> VoiceResult[SpeechAudio]:
        return await self._first_working(self.tts, lambda p: p.synthesize(text, language))


def build_voice_service(settings: Settings) -> VoiceService:
    """Providers in the order of EZO_VOICE_PROVIDERS ("auto" = VoiceStudio, ElevenLabs, OpenAI)."""
    available: dict[str, AudioProvider] = {}
    if settings.voicestudio_url:
        key = (
            settings.voicestudio_api_key.get_secret_value() if settings.voicestudio_api_key else ""
        )
        available["voicestudio"] = OpenAIAudioProvider(
            "voicestudio",
            api_key=key or "not-needed",  # VoiceStudio on loopback/internal network needs no key
            base_url=settings.voicestudio_url.rstrip("/") + "/v1",
            stt_model="whisper-1",
            tts_model="tts-1",
            voice=settings.voicestudio_voice,
            send_language_to_tts=True,
            timeout=settings.voice_timeout_seconds,
        )
    if settings.elevenlabs_api_key:
        available["elevenlabs"] = ElevenLabsAudioProvider(
            "elevenlabs",
            api_key=settings.elevenlabs_api_key.get_secret_value(),
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model_id,
            stt_model=settings.elevenlabs_stt_model,
            timeout=settings.voice_timeout_seconds,
        )
    if settings.openai_api_key:
        available["openai"] = OpenAIAudioProvider(
            "openai",
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            stt_model=settings.openai_stt_model,
            tts_model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            timeout=settings.voice_timeout_seconds,
        )
    order = (
        ["voicestudio", "elevenlabs", "openai"]
        if settings.voice_providers == ["auto"]
        else settings.voice_providers
    )
    stt_chosen = [
        p for name in order if (p := available.get(name)) and isinstance(p, SpeechToTextProvider)
    ]
    tts_chosen = [
        p for name in order if (p := available.get(name)) and isinstance(p, TextToSpeechProvider)
    ]
    return VoiceService(stt=stt_chosen, tts=tts_chosen)
