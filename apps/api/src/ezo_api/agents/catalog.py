"""Catalog of EZO agents and their availability.

Agents that are not implemented yet are listed with the milestone that will
deliver them. EzoCore never pretends an unavailable agent ran.
"""

from __future__ import annotations

from dataclasses import dataclass

from ezo_api.core.intent import Intent
from ezo_api.personality.profile import ContextMode


@dataclass(frozen=True, slots=True)
class AgentSpec:
    key: str
    intent: Intent
    names: dict[str, str]  # uz / en / ru
    description: str
    available: bool
    milestone: int
    context_mode: ContextMode
    route: str
    limitation_note: str = ""
    """Extra instructions for GeneralAgent when it covers for this agent."""


AGENTS: dict[Intent, AgentSpec] = {
    spec.intent: spec
    for spec in [
        AgentSpec(
            "general",
            Intent.GENERAL,
            {"uz": "Umumiy hamroh", "en": "General Companion", "ru": "Общий компаньон"},
            "Natural conversation, brainstorming, goals and personal assistance.",
            available=True,
            milestone=1,
            context_mode="casual",
            route="chat",
        ),
        AgentSpec(
            "language_coach",
            Intent.LANGUAGE_COACH,
            {"uz": "Til murabbiyi", "en": "Language Coach", "ru": "Языковой тренер"},
            "Speaking practice, IELTS-style simulator, grammar and vocabulary coaching.",
            available=False,
            milestone=3,
            context_mode="teacher",
            route="chat",
            limitation_note=(
                "The dedicated Language Coach (IELTS-style simulator, progress tracking, "
                "session reports) is not available yet. You can still practise conversation "
                "with the user in a friendly teacher style, but do not claim to give official "
                "or calibrated IELTS band scores, and mention once that full speaking practice "
                "with reports arrives in a later EZO update."
            ),
        ),
        AgentSpec(
            "presentation",
            Intent.PRESENTATION,
            {"uz": "Taqdimot agenti", "en": "Presentation Agent", "ru": "Агент презентаций"},
            "Narrative, slide architecture, layout QA and PPTX/PDF/web export.",
            available=True,
            milestone=4,
            context_mode="professional",
            route="reasoning",
        ),
        AgentSpec(
            "developer",
            Intent.DEVELOPER,
            {"uz": "Dasturchi agent", "en": "Developer Agent", "ru": "Агент-разработчик"},
            "Repository understanding, debugging, tests, diffs and pull requests.",
            available=False,
            milestone=6,
            context_mode="technical",
            route="coding",
            limitation_note=(
                "The Developer Agent (repository access, running tests, git) is not available "
                "yet. You cannot see the user's repository or run code. Help with the code the "
                "user pastes, and ask them to paste relevant files or error messages. Never "
                "claim code works unless it was actually run."
            ),
        ),
        AgentSpec(
            "legal_research",
            Intent.LEGAL_RESEARCH,
            {
                "uz": "Huquqiy tadqiqot agenti",
                "en": "Legal Research Agent",
                "ru": "Агент правовых исследований",
            },
            "Uzbekistan legislation with official sources (LEX.UZ) and currentness checks.",
            available=False,
            milestone=5,
            context_mode="professional",
            route="reasoning",
            limitation_note=(
                "The Legal Research Agent with synchronized official sources (LEX.UZ, "
                "president.uz) is not available yet, and you have no live access to them. "
                "Do NOT state document numbers, dates or article contents unless you are "
                "certain, and say they must be verified on https://lex.uz. Give general "
                "orientation only. This is informational help, not legal advice."
            ),
        ),
        AgentSpec(
            "research",
            Intent.RESEARCH,
            {"uz": "Tadqiqot agenti", "en": "Research Agent", "ru": "Исследовательский агент"},
            "Current web research, source comparison and citations.",
            available=True,
            milestone=2,
            context_mode="professional",
            route="research",
        ),
        AgentSpec(
            "document",
            Intent.DOCUMENT,
            {"uz": "Hujjat agenti", "en": "Document Agent", "ru": "Агент документов"},
            "Reading, creating, editing, comparing and converting DOCX, PDF, XLSX and CSV.",
            available=True,
            milestone=4,
            context_mode="professional",
            route="chat",
        ),
        AgentSpec(
            "business",
            Intent.BUSINESS,
            {"uz": "Biznes agenti", "en": "Business Agent", "ru": "Бизнес-агент"},
            "Idea evaluation, market and competitor research, strategy.",
            available=False,
            milestone=8,
            context_mode="professional",
            route="reasoning",
            limitation_note=(
                "The Business Agent with live market data is not available yet. You can "
                "reason about strategy, but label every estimate and assumption clearly and "
                "never invent market statistics."
            ),
        ),
        AgentSpec(
            "visual",
            Intent.VISUAL,
            {"uz": "Vizual agent", "en": "Visual Agent", "ru": "Визуальный агент"},
            "Image generation and editing, logos, diagrams.",
            available=False,
            milestone=4,
            context_mode="casual",
            route="chat",
            limitation_note=(
                "The Visual Agent (image generation) is not available yet. You cannot create "
                "images. You may describe a visual concept or write a prompt the user could "
                "use later, and say that image generation arrives in a later EZO update."
            ),
        ),
    ]
}
