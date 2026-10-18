from datetime import datetime
from zoneinfo import ZoneInfo

from ezo_api.agents.base import AgentTurn
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.general import GeneralAgent
from ezo_api.agents.registry import AgentRegistry
from ezo_api.core.intent import Intent, classify_intent
from ezo_api.personality.profile import load_personality
from ezo_api.personality.prompt import PromptContext, PromptMemory, build_system_prompt
from ezo_api.settings import API_DIR

PROFILE = load_personality(API_DIR / "config" / "personality.toml")


def _ctx(**overrides: object) -> PromptContext:
    values: dict[str, object] = {
        "mode": "casual",
        "language": "uz",
        "language_is_fixed": False,
        "humor": "light",
        "now": datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
    }
    values.update(overrides)
    return PromptContext(**values)  # type: ignore[arg-type]


def test_prompt_contains_identity_rules_language_and_date() -> None:
    prompt = build_system_prompt(PROFILE, _ctx())
    assert "You are EZO" in prompt
    assert "Great question" in prompt  # the anti-sycophancy rule
    assert "Uzbek" in prompt
    assert "2026-10-17 12:00" in prompt


def test_prompt_includes_memories_and_mode() -> None:
    prompt = build_system_prompt(
        PROFILE,
        _ctx(mode="technical", memories=[PromptMemory("profile", "preference", "likes Python")]),
    )
    assert "likes Python" in prompt
    assert "Technical partner" in prompt


def test_fixed_language_rule() -> None:
    prompt = build_system_prompt(PROFILE, _ctx(language="en", language_is_fixed=True))
    assert "Always answer in English" in prompt


def test_registry_falls_back_to_general_for_unavailable_agents() -> None:
    selection = AgentRegistry().select(Intent.BUSINESS)
    assert selection.agent.spec.key == "general"
    assert selection.requested.key == "business"
    assert selection.is_fallback


def test_registry_selects_document_and_presentation_agents() -> None:
    registry = AgentRegistry()
    assert registry.select(Intent.PRESENTATION).agent.spec.key == "presentation"
    assert registry.select(Intent.DOCUMENT).agent.spec.key == "document"
    assert not registry.select(Intent.DOCUMENT).is_fallback


def test_manual_agent_override() -> None:
    selection = AgentRegistry().select(Intent.GENERAL, forced_agent="developer")
    assert selection.requested.key == "developer"


def test_general_agent_covering_uses_limitation_note_and_route() -> None:
    text = "Ezo, GitHub projectimdagi bugni top."
    plan = GeneralAgent().plan(
        AgentTurn(text, "uz", classify_intent(text), AGENTS[Intent.DEVELOPER])
    )
    assert plan.route == "coding"
    assert plan.context_mode == "technical"
    assert "cannot see the user's repository" in plan.instructions


def test_general_agent_routes_deep_requests_to_reasoning() -> None:
    text = "Biznes rejamni batafsil tahlil qil"
    plan = GeneralAgent().plan(AgentTurn(text, "uz", classify_intent(text), AGENTS[Intent.GENERAL]))
    assert plan.route == "reasoning"


def test_voice_prompt_asks_for_short_spoken_answers() -> None:
    assert "Voice conversation" in build_system_prompt(PROFILE, _ctx(voice=True))
    assert "Voice conversation" not in build_system_prompt(PROFILE, _ctx())
