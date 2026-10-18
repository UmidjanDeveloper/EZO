"""Catalog of EZO agents, their roadmap phase and maturity.

Agents that are not implemented yet are listed as ``planned`` with the roadmap
phase that will deliver them (ROADMAP.md). EzoCore never pretends an
unavailable agent ran: availability is derived from the maturity label.
"""

from __future__ import annotations

from dataclasses import dataclass

from ezo_api.core.intent import Intent
from ezo_api.maturity import Maturity
from ezo_api.personality.profile import ContextMode


@dataclass(frozen=True, slots=True)
class AgentSpec:
    key: str
    intent: Intent
    names: dict[str, str]  # uz / en / ru
    description: str
    maturity: Maturity
    phase: str
    """Roadmap section that delivered (or will deliver) the agent."""
    context_mode: ContextMode
    route: str
    limitation_note: str = ""
    """Extra instructions for GeneralAgent when it covers for this agent."""

    @property
    def available(self) -> bool:
        return self.maturity != "planned"


AGENTS: dict[Intent, AgentSpec] = {
    spec.intent: spec
    for spec in [
        AgentSpec(
            "general",
            Intent.GENERAL,
            {"uz": "Umumiy hamroh", "en": "General Companion", "ru": "Общий компаньон"},
            "Natural conversation, brainstorming, goals and personal assistance.",
            maturity="alpha",
            phase="Foundation",
            context_mode="casual",
            route="chat",
        ),
        AgentSpec(
            "language_coach",
            Intent.LANGUAGE_COACH,
            {"uz": "Til murabbiyi", "en": "Language Coach", "ru": "Языковой тренер"},
            "Practice sessions, IELTS-style speaking simulator (estimated bands), progress.",
            maturity="alpha",
            phase="Phase 5",
            context_mode="teacher",
            route="chat",
        ),
        AgentSpec(
            "presentation",
            Intent.PRESENTATION,
            {"uz": "Taqdimot agenti", "en": "Presentation Agent", "ru": "Агент презентаций"},
            "Narrative, slide architecture, layout QA and PPTX/PDF/web export.",
            maturity="alpha",
            phase="Presentations",
            context_mode="professional",
            route="reasoning",
        ),
        AgentSpec(
            "developer",
            Intent.DEVELOPER,
            {"uz": "Dasturchi agent", "en": "Developer Agent", "ru": "Агент-разработчик"},
            "Repository understanding, debugging, tests, diffs and pull requests.",
            maturity="planned",
            phase="Phase 9",
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
            maturity="planned",
            phase="Phase 8",
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
            maturity="alpha",
            phase="Knowledge",
            context_mode="professional",
            route="research",
        ),
        AgentSpec(
            "document",
            Intent.DOCUMENT,
            {"uz": "Hujjat agenti", "en": "Document Agent", "ru": "Агент документов"},
            "Reading, creating, editing, comparing and converting DOCX, PDF, XLSX and CSV.",
            maturity="alpha",
            phase="Documents",
            context_mode="professional",
            route="chat",
        ),
        AgentSpec(
            "business",
            Intent.BUSINESS,
            {"uz": "Biznes agenti", "en": "Business Agent", "ru": "Бизнес-агент"},
            "Idea evaluation, market and competitor research, strategy.",
            maturity="planned",
            phase="Business",
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
            "Image generation and editing, diagrams, social graphics, logo concepts.",
            maturity="alpha",
            phase="Phase 6",
            context_mode="casual",
            route="chat",
        ),
    ]
}
