"""Unit tests for smart agent routing and Student adapter.

Verifies the required intent and agent routing behavior:
- "Python kitobini o'rgan" -> Student
- "IELTS speaking qilaylik" -> IELTS / Language Coach
- "Prezentatsiya tayyorla" -> Presentation
- "Word hujjat tayyorla" -> Document / Office
- "Manbalar bilan tadqiqot qil" -> Research
"""

from ezo_api.agents.registry import AgentRegistry
from ezo_api.agents.student_adapter import (
    STUDENT_SPEC,
    StudentAdapterAgent,
    StudentClientAdapter,
    wants_student,
)
from ezo_api.core.intent import Intent, classify_intent


def test_smart_router_prompt_classifications() -> None:
    # 1. IELTS speaking qilaylik -> Language coach (IELTS)
    res_ielts = classify_intent("IELTS speaking qilaylik")
    assert res_ielts.intent == Intent.LANGUAGE_COACH

    # 2. Prezentatsiya tayyorla -> Presentation
    res_pres = classify_intent("Prezentatsiya tayyorla")
    assert res_pres.intent == Intent.PRESENTATION

    # 3. Word hujjat tayyorla -> Document / Office
    res_doc = classify_intent("Word hujjat tayyorla")
    assert res_doc.intent == Intent.DOCUMENT

    # 4. Manbalar bilan tadqiqot qil -> Research
    res_res = classify_intent("Manbalar bilan tadqiqot qil")
    assert res_res.intent == Intent.RESEARCH


def test_student_reading_intent_detection() -> None:
    # "Python kitobini o'rgan" must trigger wants_student
    assert wants_student("Python kitobini o'rgan")
    assert wants_student("Darslikni o'rganamiz")
    assert wants_student("Student rejimida kitob o'qi")
    assert wants_student("Talaba o'qishi uchun qo'llanma tahlil qil")

    # Regular non-student queries must not trigger wants_student
    assert not wants_student("Salom, qalaysan?")
    assert not wants_student("Prezentatsiya tayyorla")
    assert not wants_student("IELTS speaking qilaylik")


def test_student_adapter_agent_spec_and_plan() -> None:
    agent = StudentAdapterAgent()
    assert agent.spec.key == "student"
    assert agent.spec.available is True
    assert agent.spec.intent == Intent.GENERAL
    assert STUDENT_SPEC.key == "student"

    status = StudentClientAdapter.get_public_status()
    assert "pdf" in status["raw_upload_formats"]
    assert "docx" in status["raw_upload_formats"]
    assert "epub" in status["raw_upload_formats"]
    assert status["native_execution"] == "disabled"
    assert status["max_raw_input_bytes"] == 5_242_880


def test_registry_maps_intents_to_active_agents() -> None:
    registry = AgentRegistry()

    # IELTS / Language Coach
    sel_ielts = registry.select(Intent.LANGUAGE_COACH)
    assert sel_ielts.agent.spec.key == "language_coach"
    assert not sel_ielts.is_fallback

    # Presentation
    sel_pres = registry.select(Intent.PRESENTATION)
    assert sel_pres.agent.spec.key == "presentation"
    assert not sel_pres.is_fallback

    # Document
    sel_doc = registry.select(Intent.DOCUMENT)
    assert sel_doc.agent.spec.key == "document"
    assert not sel_doc.is_fallback

    # Research
    sel_res = registry.select(Intent.RESEARCH)
    assert sel_res.agent.spec.key == "research"
    assert not sel_res.is_fallback
