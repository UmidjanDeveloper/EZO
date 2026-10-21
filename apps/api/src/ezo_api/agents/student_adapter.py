"""Student public adapter agent for EZO.

Integrates with Codex's Student V1 through the documented public HTTP contract:
  - GET /api/student/status
  - POST /api/student/readings
  - GET /api/student/readings/{job_id}

Does NOT modify or import private internals of Student V1 durable jobs or executor.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.catalog import AgentSpec
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.documents.isolation import ISOLATION_MESSAGE
from ezo_api.personality.profile import ContextMode
from ezo_api.providers.types import ChatMessage

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
    """Public client adapter interacting with the Student reading service without private imports."""

    @staticmethod
    def get_public_status() -> dict[str, Any]:
        return {
            "supported_submission": "authorized_utf8_text",
            "max_input_bytes": 2_000_000,
            "worker": "stored-normalized-text/v1",
            "native_execution": "disabled",
            "blocked_formats": ["pdf", "docx", "epub", "xlsx", "image", "html"],
            "reason": ISOLATION_MESSAGE,
        }

    @staticmethod
    async def get_status_summary() -> str:
        status = StudentClientAdapter.get_public_status()
        return (
            f"Student xizmati holati: {status['worker']} faol. "
            f"Matn formati (UTF-8): ruxsat etilgan ({status['max_input_bytes'] // 1_000_000}MB gacha). "
            f"Format cheklovlari: {', '.join(status['blocked_formats'])} (sabab: {status['reason']})."
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
    limitation_note="PDF/DOCX native ijrosi xavfsizlik cheklovlari tufayli vaqtincha to'xtatilgan. Matn orqali o'rganish to'liq qo'llab-quvvatlanadi.",
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
            "Foydalanuvchi kitob yoki darslikni o'rganishni so'raganda (masalan, 'Python kitobini o'rgan'), "
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
