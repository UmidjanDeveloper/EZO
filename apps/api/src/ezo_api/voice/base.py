"""Voice provider interfaces.

EZO never depends on one voice vendor. Each provider implements speech-to-text
and/or text-to-speech; `VoiceService` tries them in the configured order and
falls back to the next one. The browser's own speech features remain the last
fallback on the client side.

Audio is processed in memory and never written to disk or the database.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

VoiceErrorKind = Literal["unavailable", "auth", "rate_limit", "bad_audio", "timeout", "failed"]


class VoiceError(Exception):
    """A provider could not handle the request. `message` is safe to show."""

    def __init__(self, kind: VoiceErrorKind, message: str) -> None:
        self.kind = kind
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str | None
    provider: str


@dataclass(frozen=True, slots=True)
class SpeechAudio:
    data: bytes
    mime_type: str
    provider: str


class SpeechToTextProvider(ABC):
    name: str

    @abstractmethod
    async def transcribe(
        self, audio: bytes, mime_type: str, filename: str, language: str | None
    ) -> Transcript:
        """Turn a short recording into text. `language` is a hint (uz/en/ru) or None."""


class TextToSpeechProvider(ABC):
    name: str

    @abstractmethod
    async def synthesize(self, text: str, language: str | None) -> SpeechAudio:
        """Read `text` aloud; returns encoded audio (mp3)."""


@dataclass(frozen=True, slots=True)
class RealtimeEvent:
    type: Literal["transcript_partial", "transcript_final", "audio", "end_of_turn", "error"]
    text: str = ""
    audio: bytes = b""


class RealtimeVoiceProvider(ABC):
    """Full-duplex streaming voice (microphone in, speech out, barge-in).

    Interface only: no realtime provider is implemented yet (Milestone 7).
    EZO's voice mode currently works turn by turn (record → transcribe → answer
    → speak) and supports interruption on the client.
    """

    name: str

    @abstractmethod
    def session(self, language: str | None) -> AsyncIterator[RealtimeEvent]:
        """Open a realtime session."""
