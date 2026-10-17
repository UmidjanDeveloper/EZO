"""Timeline planning: when each scene starts and ends (pure functions, unit-tested)."""

from __future__ import annotations

from dataclasses import dataclass

# A calm speaking pace across uz/en/ru narration (words per second).
WORDS_PER_SECOND = 2.4
SCENE_PADDING_SECONDS = 0.8


@dataclass(frozen=True, slots=True)
class TimedScene:
    start: float
    end: float


def narration_seconds(text: str) -> float:
    """Approximate time needed to read `text` aloud."""
    words = len(text.split())
    return round(words / WORDS_PER_SECOND + SCENE_PADDING_SECONDS, 2) if words else 0.0


def plan_timeline(scenes: list[tuple[float, str]]) -> list[TimedScene]:
    """Sequential timeline. Each scene lasts its planned duration, or longer if its
    narration needs more time — narration is never cut off."""
    timeline: list[TimedScene] = []
    cursor = 0.0
    for duration, narration in scenes:
        length = max(duration, narration_seconds(narration))
        timeline.append(TimedScene(start=round(cursor, 2), end=round(cursor + length, 2)))
        cursor += length
    return timeline
