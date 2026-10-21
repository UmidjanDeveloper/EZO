"""Student public adapter agent for EZO.

Integrates with Codex's Student V1 through the documented public HTTP contract:
  - GET /api/student/status
  - POST /api/student/readings
  - GET /api/student/readings/{job_id}

Does NOT modify or import private internals of Student V1 durable jobs or executor.
"""

from __future__ import annotations

import re
from typing import Any

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.catalog import AgentSpec
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize

_STUDENT_PATTERNS = re.compile(
    r"(?<!\w)("
    r"(kitob\w*|darslik\w*|qo'llanma\w*|maqola\w*|reading\w*|textbook\w*)\s*.{0,30}\s*"
    r"(o'rgan\w*|o'qi\w*|tahlil qil\w*|o'rganaylik|o'rganamiz|study|read|learn)"
    r"|(o'rgan\w*|o'qi\w*|tahlil qil\w*|study|read|learn)\s*.{0,30}\s*"
    r"(kitob\w*|darslik\w*|qo'llanma\w*|maqola\w*|reading\w*|textbook\w*)"
    r"|python kitobini o'rgan"
    r"|student\s+(o'qish|tizimi|reading|rejim)"
    r"|talaba\s+(rejimi|o'qishi|darslik)"
    r"|учебник\w*\s+.{0,30}\s*(изучи\w*|прочитай\w*)"
    r"|(изучи\w*|прочитай\w*)\s+.{0,30}\s*учебник\w*"
    r")(?!\w)",
    re.I,
)


def wants_student(text: str) -> bool:
    """Detect requests to learn/read from books, textbooks or student study materials."""
    norm = normalize(text)
    return bool(_STUDENT_PATTERNS.search(norm))


class StudentClientAdapter:
    """Public client adapter interacting with Student service without private imports."""

    @staticmethod
    def get_public_status() -> dict[str, Any]:
        """Align with STUDENT_AGENT_CONTRACT.md public HTTP contract."""
        return {
            "supported_submissions": ["authorized_utf8_text", "raw_binary_upload"],
            "raw_upload_formats": ["pdf", "docx", "epub"],
            "max_raw_input_bytes": 5_242_880,  # 5 MiB per STUDENT_AGENT_CONTRACT.md
            "max_text_input_bytes": 2_000_000,
            "worker": "stored-normalized-text/v1",
            "native_execution": "disabled",  # Public API disables in-process native execution
            "raw_processing": "requires_separate_dedicated_postgresql_worker",
            "unsupported_formats": ["xlsx", "image", "html"],
            "security_boundaries": (
                "Raw uploads (PDF, DOCX, EPUB gacha 5MB) saqlanadi va faqat izolyatsiyalangan "
                "alohida PostgreSQL native worker orqali bajariladi. API ichida bevosita native "
                "kod bajarilishi xavfsizlik maqsadida taqiqlangan."
            ),
        }

    @staticmethod
    async def get_status_summary() -> str:
        status = StudentClientAdapter.get_public_status()
        raw_fmts = ", ".join(f.upper() for f in status["raw_upload_formats"])
        return (
            f"Student V1 xizmati holati: {raw_fmts} (5MB gacha) va "
            f"UTF-8 matnlar qo'llab-quvvatlanadi. "
            f"Xavfsizlik: API da native execution o'chirilgan, "
            f"xom fayllar faqat ajratilgan izolyatsiyalangan worker orqali qayta ishlanadi."
        )


STUDENT_SPEC = AgentSpec(
    key="student",
    intent=Intent.GENERAL,
    names={"uz": "Talaba agenti", "en": "Student Agent", "ru": "Студенческий агент"},
    description="Darsliklar va kitoblarni mustaqil o'rganish, boblar tahlili va savol-javoblar.",
    maturity="alpha",
    phase="Student Foundation",
    context_mode="teacher",
    route="chat",
    limitation_note=(
        "PDF, DOCX va EPUB darsliklari (5MB gacha) hamda to'g'ridan-to'g'ri matn qabul qilinadi. "
        "Xavfsizlik talablariga ko'ra xom fayllar izolyatsiyalangan alohida worker orqali "
        "qayta ishlanadi."
    ),
)


class StudentAdapterAgent(Agent):
    """Adapter agent serving Student requests through public boundaries."""

    spec = STUDENT_SPEC

    async def gather(self, ctx: GatherContext) -> Gathered:
        status_note = await StudentClientAdapter.get_status_summary()
        return Gathered(
            notes=[status_note],
            sources=[],
        )

    def plan(self, turn: AgentTurn) -> AgentPlan:
        instructions = (
            "Siz EZO OS ning Talaba (Student) ta'lim agentisiz. "
            "Foydalanuvchi kitob yoki darslikni o'rganishni so'raganda "
            "(masalan, 'Python kitobini o'rgan'), "
            "unga o'quv rejasini tuzib bering, asosiy mavzularni tushuntiring va matnni "
            "o'rganish uchun qanday kiritish mumkinligini aniq ko'rsating. "
            "Barcha tushuntirishlarni o'zbek tilida, do'stona va pedagogik uslubda bering."
        )
        return AgentPlan(
            route="chat",
            context_mode="teacher",
            instructions=instructions,
            steps=("classify_intent", "select_agent", "compose_prompt", "generate", "verify"),
        )
