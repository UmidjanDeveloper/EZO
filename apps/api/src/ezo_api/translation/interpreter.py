"""Voice interpretation: speech → transcript → translation → speech, one turn at a time.

This is *turn-based* interpretation: a speaker finishes, EZO transcribes, translates and
(optionally) reads the translation aloud. It is not simultaneous interpretation; the
`StreamingInterpreter` interface below is where low-latency streaming with interruption
will plug in once EZO has a realtime voice provider (roadmap: realtime voice).
Audio is processed in memory only, like the rest of EZO's voice features.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from ezo_api.providers.router import ModelRouter
from ezo_api.translation.glossary import Term
from ezo_api.translation.languages import base, default_target, detect
from ezo_api.translation.service import TranslationResult, translate_text
from ezo_api.voice.base import RealtimeEvent, SpeechAudio, Transcript
from ezo_api.voice.service import VoiceService

MODE = "turn-based"


@dataclass(frozen=True, slots=True)
class InterpretedTurn:
    transcript: Transcript
    translation: TranslationResult
    speech: SpeechAudio | None
    mode: str = MODE


class StreamingInterpreter(ABC):
    """Future: simultaneous interpretation over a realtime voice session (partial
    transcripts in, translated speech out, barge-in). No implementation yet."""

    @abstractmethod
    def interpret(
        self, audio: AsyncIterator[bytes], source: str | None, target: str
    ) -> AsyncIterator[RealtimeEvent]:
        """Translated speech and text events for a live audio stream."""


class TurnBasedInterpreter:
    def __init__(self, voice: VoiceService, router: ModelRouter) -> None:
        self.voice = voice
        self.router = router

    async def interpret(
        self,
        audio: bytes,
        *,
        mime_type: str,
        filename: str,
        target: str,
        source: str | None = None,
        terms_for: Callable[[str, str], Awaitable[list[Term]]] | None = None,
        speak: bool = True,
    ) -> InterpretedTurn:
        heard = (await self.voice.transcribe(audio, mime_type, filename, None)).value
        # The language actually spoken decides the direction: in a conversation between
        # `source` and `target`, either side may speak.
        spoken = heard.language if heard.language in ("uz", "ru", "en") else detect(heard.text)
        if source and base(spoken) == base(source):
            spoken = source
        if base(spoken) == base(target):
            target = (
                source
                if source and base(source) != base(target)
                else default_target(spoken, target)
            )
        terms = await terms_for(spoken, target) if terms_for is not None else []
        translation = await translate_text(
            self.router, heard.text, source=spoken, target=target, terms=terms
        )
        speech = None
        if speak and self.voice.tts:
            speech = (await self.voice.synthesize(translation.text, base(target))).value
        return InterpretedTurn(heard, translation, speech)
