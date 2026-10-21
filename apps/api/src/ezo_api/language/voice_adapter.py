"""Voice Provider Adapter Interface for IELTS Examiner 2.0.

Provides an extensible contract for future real-time speech / audio integrations
while ensuring a robust, deterministic text-based fallback when speech services
are unavailable.

Explicitly distinguishes implemented text functionality from future voice integrations.
Never claims official certification or invents fake voice scoring.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VoiceStatus:
    available: bool
    provider: str
    fallback_mode: str
    notice_uz: str
    notice_en: str
    details: dict[str, Any]


class VoiceAdapterInterface(abc.ABC):
    """Abstract interface for speech services (STT / TTS)."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True if live speech services are configured and reachable."""

    @abc.abstractmethod
    def get_status(self) -> VoiceStatus:
        """Return human-readable and machine-readable adapter status."""

    @abc.abstractmethod
    async def transcribe(self, audio_bytes: bytes, content_type: str = "audio/webm") -> str | None:
        """Transcribe learner speech to text. Returns None if voice is unavailable."""

    @abc.abstractmethod
    async def synthesize(self, text: str, voice_id: str | None = None) -> bytes | None:
        """Synthesize examiner text to audio. Returns None if voice is unavailable."""


class TextFallbackVoiceAdapter(VoiceAdapterInterface):
    """Safe, default fallback adapter when external voice services are not configured.

    Clearly marks voice as offline/fallback and provides graceful text-first flow.
    """

    def __init__(self, provider_name: str = "offline_text_fallback") -> None:
        self.provider_name = provider_name

    def is_available(self) -> bool:
        return False

    def get_status(self) -> VoiceStatus:
        return VoiceStatus(
            available=False,
            provider=self.provider_name,
            fallback_mode="text",
            notice_uz=(
                "Ovozli xizmat (Speech-to-Text / Text-to-Speech) hozirda sozlanmagan. "
                "IELTS simulyatori to'liq matnli rejimda ishlamoqda. "
                "Rasmiy IELTS sertifikati emas — "
                "ta'limiy va mustaqil tayyorgarlik uchun taxminiy baholash."
            ),
            notice_en=(
                "Voice service (Speech-to-Text / Text-to-Speech) is currently unconfigured. "
                "IELTS simulator operates in full text fallback mode. "
                "Not an official IELTS certificate — educational estimated assessment only."
            ),
            details={
                "supported_modalities": ["text", "browser_speech_api_ready"],
                "max_recording_seconds": 120,
                "offline_fallback_active": True,
            },
        )

    async def transcribe(self, audio_bytes: bytes, content_type: str = "audio/webm") -> str | None:
        # Fallback adapter does not process raw audio without an active speech engine
        return None

    async def synthesize(self, text: str, voice_id: str | None = None) -> bytes | None:
        # Fallback adapter defers audio generation to browser SpeechSynthesis or returns None
        return None


# Global default instance
default_voice_adapter = TextFallbackVoiceAdapter()
