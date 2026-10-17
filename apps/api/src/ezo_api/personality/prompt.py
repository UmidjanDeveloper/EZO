"""System prompt composition.

The prompt is assembled from stable parts first (identity, traits, rules) and
volatile parts last (memories, date), which keeps provider-side prompt caching
effective.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from ezo_api.personality.profile import ContextMode, HumorLevel, PersonalityProfile


@dataclass(frozen=True, slots=True)
class PromptMemory:
    memory_type: str
    category: str
    content: str


@dataclass(frozen=True, slots=True)
class PromptContext:
    mode: ContextMode
    language: str
    language_is_fixed: bool
    humor: HumorLevel
    now: datetime
    project_name: str | None = None
    project_description: str | None = None
    memories: Sequence[PromptMemory] = ()
    agent_instructions: str = ""


def build_system_prompt(profile: PersonalityProfile, ctx: PromptContext) -> str:
    sections: list[str] = [profile.identity]

    sections.append("Personality: " + "; ".join(profile.traits) + ".")
    sections.append("Rules:\n" + "\n".join(f"- {rule}" for rule in profile.rules))

    humor_rule = profile.humor_levels.get(ctx.humor)
    if humor_rule:
        sections.append(f"Humor: {humor_rule}")

    mode = profile.mode(ctx.mode)
    sections.append(f"Current context: {mode.label}. Style: {mode.style}")

    language_name = profile.languages.get(ctx.language, ctx.language)
    if ctx.language_is_fixed:
        sections.append(
            f"Always answer in {language_name}, unless the user explicitly asks "
            "for another language."
        )
    else:
        sections.append(
            f"The user's last message appears to be in {language_name}. Answer in the language "
            "the user is writing in (Uzbek, English or Russian). If unsure, use Uzbek."
        )

    if ctx.agent_instructions:
        sections.append(ctx.agent_instructions.strip())

    if ctx.project_name:
        project = f'The conversation belongs to the user\'s project "{ctx.project_name}".'
        if ctx.project_description:
            project += f" Project description: {ctx.project_description}"
        sections.append(project)

    if ctx.memories:
        lines = "\n".join(f"- ({m.category}) {m.content}" for m in ctx.memories)
        sections.append(
            "What you remember about the user (from earlier conversations; may be outdated, "
            "use only when relevant, do not recite it unprompted):\n" + lines
        )

    sections.append(f"Current date and time: {ctx.now:%Y-%m-%d %H:%M} ({ctx.now.tzname()}).")
    return "\n\n".join(section for section in sections if section)
