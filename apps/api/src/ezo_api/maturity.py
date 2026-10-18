"""How finished each EZO capability is — the single source used by the API and the docs.

Labels:
- ``planned``      not implemented; EZO says so and never pretends it ran
- ``experimental`` works in tests, interfaces may change, not for real work yet
- ``alpha``        usable end to end, tested, but young (expect rough edges)
- ``beta``         used for real work for a while, few known problems
- ``stable``       mature; changes are backwards compatible

Phases refer to ROADMAP.md (the one authoritative roadmap).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Maturity = Literal["planned", "experimental", "alpha", "beta", "stable"]
MATURITY_LEVELS: tuple[Maturity, ...] = ("planned", "experimental", "alpha", "beta", "stable")


@dataclass(frozen=True, slots=True)
class Feature:
    key: str
    name: str
    phase: str
    maturity: Maturity
    note: str = ""


# Capabilities that are not agents. Keep in sync with ROADMAP.md (a test checks the keys).
FEATURES: tuple[Feature, ...] = (
    Feature("chat_core", "EzoCore chat, routing, personality", "Foundation", "alpha"),
    Feature("memory", "Memory (profile, project, semantic)", "Foundation", "alpha"),
    Feature("knowledge", "Files, knowledge base and citations", "Knowledge", "alpha"),
    Feature("voice_turns", "Turn-by-turn voice (browser / OpenAI / VoiceStudio)", "Voice", "alpha"),
    Feature("presence", "EZO orb activity states", "Voice", "alpha"),
    Feature("artifacts", "Artifacts with versions and exports", "Artifacts", "alpha"),
    Feature(
        "story_projects",
        "Story projects (scenes, narration, timeline)",
        "Artifacts",
        "experimental",
        "API only, no dedicated UI yet",
    ),
    Feature("documents", "DOCX / PDF / XLSX / CSV generation", "Documents", "alpha"),
    Feature(
        "presentations",
        "Slide engine, PPTX / PDF / web export, layout QA",
        "Presentations",
        "alpha",
    ),
    Feature(
        "orchestration",
        "Native multi-agent missions",
        "Orchestration foundation",
        "experimental",
        "in-memory, not started from chat yet",
    ),
    Feature(
        "language_coach",
        "Language Coach, IELTS-style simulator, progress",
        "Phase 1",
        "alpha",
        "estimated bands only; pronunciation transcript-assisted",
    ),
    Feature(
        "visual",
        "Images, image edits, diagrams, social graphics, logo concepts, deck visuals",
        "Phase 2",
        "alpha",
        "generated pictures need an OpenAI or Gemini key; text is always drawn by EZO",
    ),
    Feature(
        "ezo_office",
        "OCR + EZO Office: PDF tools, scans, DOCX fidelity, long documents",
        "Phase 3",
        "alpha",
        "OCR needs Tesseract (in the Docker image); summaries and translations need a model; "
        "layout Word is not pixel-exact; Word footnotes/comments not edited",
    ),
    Feature(
        "professional_writing",
        "Professional writing: 30 official, academic and career document types, "
        "organization profiles",
        "Professional writing",
        "alpha",
        "drafts need an AI key (templates work offline); official papers stay drafts "
        "until a person approves them",
    ),
    Feature(
        "education_academic_career",
        "Education, academic research and career agents",
        "Phase 4",
        "planned",
    ),
    Feature("jobs", "Durable tasks, jobs and background worker", "Phase 5", "planned"),
    Feature("missions", "Persistent native missions in chat", "Phase 6", "planned"),
    Feature(
        "official_sources",
        "Official legal sources: connector framework, LEX.UZ proof of concept, sync",
        "Phase 7",
        "experimental",
        "LEX.UZ off by default; live access not yet verified; other sources not reviewed",
    ),
    Feature("realtime_voice", "Realtime streaming voice", "Phase 8", "planned"),
    Feature("data_analyst", "Data analyst agent and dashboards", "Phase 10", "planned"),
    Feature("browser_agent", "Approved browser actions", "Phase 11", "planned"),
    Feature("video", "Video / motion studio", "Phase 12", "planned"),
    Feature(
        "ruflo",
        "Optional Ruflo orchestration provider",
        "Phase 14",
        "planned",
        "audited; off by default",
    ),
)
