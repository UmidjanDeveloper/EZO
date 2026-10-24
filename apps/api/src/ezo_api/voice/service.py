"""Ordered voice providers with fallback."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from ezo_api.providers.limits import CallBudget, UsageLimitError
from ezo_api.settings import Settings
from ezo_api.voice.base import (
    SpeechAudio,
    SpeechToTextProvider,
    TextToSpeechProvider,
    Transcript,
    VoiceError,
)
from ezo_api.voice.elevenlabs import ElevenLabsProvider
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
        *,
        budget: CallBudget | None = None,
        max_text: int = 4000,
        max_audio: int = 10 * 1024 * 1024,
    ) -> None:
        self.budget, self.max_text, self.max_audio = budget, max_text, max_audio
        self.stt = list(stt)
        self.tts = list(tts)

    async def _first_working(
        self, providers: Sequence[P], call: Callable[[P], Awaitable[T]]
    ) -> VoiceResult[T]:
        attempts: list[VoiceAttempt] = []
        for provider in providers:
            try:
                if self.budget is None:
                    value = await call(provider)
                else:
                    try:
                        async with self.budget.admit():
                            value = await call(provider)
                    except UsageLimitError:
                        raise VoiceError("rate_limit", "Voice call budget exhausted.") from None
                    except TimeoutError:
                        raise VoiceError("timeout", "Voice operation deadline exceeded.") from None
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
        if not audio or len(audio) > self.max_audio:
            raise AllVoiceProvidersFailedError(
                [VoiceAttempt("limits", False, "bad_audio", "Audio size limit exceeded.")]
            )
        return await self._first_working(
            self.stt, lambda p: p.transcribe(audio, mime_type, filename, language)
        )

    async def synthesize(self, text: str, language: str | None) -> VoiceResult[SpeechAudio]:
        if not text.strip() or len(text) > self.max_text:
            raise AllVoiceProvidersFailedError(
                [VoiceAttempt("limits", False, "bad_audio", "Speech text limit exceeded.")]
            )
        return await self._first_working(self.tts, lambda p: p.synthesize(text, language))


def build_voice_service(settings: Settings) -> VoiceService:
    """Providers in the order of EZO_VOICE_PROVIDERS ("auto" = VoiceStudio, ElevenLabs, OpenAI)."""
    available: dict[str, OpenAIAudioProvider | ElevenLabsProvider] = {}
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
            max_audio=settings.voice_max_audio_mb * 1024 * 1024,
        )
    if settings.elevenlabs_api_key:
        available["elevenlabs"] = ElevenLabsProvider(
            settings.elevenlabs_api_key.get_secret_value(),
            voice_id=settings.elevenlabs_voice_id,
            stt_model=settings.elevenlabs_stt_model,
            tts_model=settings.elevenlabs_tts_model,
            languages=settings.elevenlabs_tts_languages,
            timeout=settings.voice_timeout_seconds,
            max_audio=settings.voice_max_audio_mb * 1024 * 1024,
            max_text=settings.voice_max_text_chars,
        )
    if settings.openai_api_key:
        available["openai"] = OpenAIAudioProvider(
            "openai",
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            stt_model=settings.openai_stt_model,
            tts_model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            steerable=settings.openai_tts_model.startswith("gpt-4o"),
            spelling_prompt=True,
            timeout=settings.voice_timeout_seconds,
            max_audio=settings.voice_max_audio_mb * 1024 * 1024,
        )
    order = (
        ["voicestudio", "elevenlabs", "openai"]
        if settings.voice_providers == ["auto"]
        else settings.voice_providers
    )
    chosen = [available[name] for name in order if name in available]
    return VoiceService(
        stt=chosen,
        tts=[p for p in chosen if not isinstance(p, ElevenLabsProvider) or p.voice_id],
        budget=CallBudget(
            settings.voice_calls_per_day, settings.voice_concurrency, settings.voice_timeout_seconds
        ),
        max_text=settings.voice_max_text_chars,
        max_audio=settings.voice_max_audio_mb * 1024 * 1024,
    )
