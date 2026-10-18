"""Turn a presentation (DeckSpec) into story scenes.

The StoryProject keeps the narrative independent of the file format, so the same
story can later become a video (ROADMAP Phase 12) or be regenerated as a new deck.
"""

from __future__ import annotations

from ezo_api.documents.render.spec import DeckSpec, SlideSpec
from ezo_api.schemas.stories import NarrationIn, SceneIn, StoryIn

WORDS_PER_SECOND = 2.4
MIN_SCENE_SECONDS = 5.0


def slide_text(slide: SlideSpec) -> str:
    """The visible text of a slide as plain lines (for the story, search and narration)."""
    lines = [slide.subtitle, slide.body, slide.quote]
    if slide.metric:
        lines.append(f"{slide.metric.value} — {slide.metric.label}")
    lines += [f"{m.value} — {m.label}" for m in slide.metrics]
    lines += [f"• {b}" for b in slide.bullets]
    for column in slide.columns:
        lines.append(column.title)
        lines += [f"• {b}" for b in column.bullets]
    lines += [f"{s.label}: {s.text}" if s.label else s.text for s in slide.steps]
    if slide.author:
        lines.append(f"— {slide.author}")
    return "\n".join(line for line in lines if line and line.strip())


def scene_from_slide(slide: SlideSpec) -> SceneIn:
    text = slide_text(slide)
    spoken = slide.speaker_notes or text
    seconds = max(MIN_SCENE_SECONDS, round(len(spoken.split()) / WORDS_PER_SECOND + 1.5, 1))
    return SceneIn(
        title=slide.title[:300],
        purpose=slide.kicker[:2000],
        layout=slide.layout,
        text=text[:20000],
        visual_direction=(slide.visual_direction or slide.image_prompt)[:4000],
        speaker_notes=slide.speaker_notes[:20000],
        duration_seconds=min(seconds, 3600),
        metadata={
            **({"sources": slide.sources} if slide.sources else {}),
            **({"image_artifact_id": slide.image_artifact_id} if slide.image_artifact_id else {}),
        },
        narration=NarrationIn(text=slide.speaker_notes[:8000]) if slide.speaker_notes else None,
    )


def story_from_deck(deck: DeckSpec, *, theme: str, artifact_id: str | None = None) -> StoryIn:
    return StoryIn(
        title=deck.title[:300] or "Presentation",
        goal=deck.goal[:4000],
        audience=deck.audience[:2000],
        language=deck.language,
        format="presentation",
        visual_style=theme,
        aspect_ratio=deck.aspect_ratio,
        metadata={"artifact_id": artifact_id} if artifact_id else {},
        scenes=[scene_from_slide(slide) for slide in deck.slides],
    )
