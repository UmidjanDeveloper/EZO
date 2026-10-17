"""Provider-neutral request/response types.

Every model provider adapter speaks these types, so the rest of EZO never
depends on a specific vendor SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

Role = Literal["user", "assistant"]
Effort = Literal["low", "medium", "high"]


class Capability(StrEnum):
    """High-level capabilities a provider adapter can expose."""

    CHAT = "chat"
    STREAMING = "streaming"
    REASONING = "reasoning"
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    VISION = "vision"
    EMBEDDINGS = "embeddings"
    SPEECH = "speech"
    IMAGE_GENERATION = "image_generation"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ChatRequest:
    model: str
    messages: list[ChatMessage]
    system: str | None = None
    max_output_tokens: int = 16_000
    effort: Effort | None = None
    # Non-secret diagnostic hints (language, agent...). Only the offline
    # provider reads these; real providers ignore them.
    hints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class StreamEnd:
    model: str
    usage: Usage
    finish_reason: str | None = None


StreamEvent = TextDelta | StreamEnd


@dataclass(frozen=True, slots=True)
class ChatResult:
    text: str
    model: str
    usage: Usage
    finish_reason: str | None = None


def normalize_turns(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Return a history every provider accepts.

    Drops empty messages and leading assistant turns, and merges consecutive
    messages with the same role (which happens when an earlier reply failed).
    """
    result: list[ChatMessage] = []
    for message in messages:
        text = message.content.strip()
        if not text:
            continue
        if not result and message.role == "assistant":
            continue
        if result and result[-1].role == message.role:
            result[-1] = ChatMessage(message.role, f"{result[-1].content}\n\n{text}")
        else:
            result.append(ChatMessage(message.role, text))
    return result
