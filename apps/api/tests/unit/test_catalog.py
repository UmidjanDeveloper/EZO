"""The agent catalog and feature list must match what is implemented and the roadmap."""

from __future__ import annotations

from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.registry import AgentRegistry
from ezo_api.maturity import FEATURES, MATURITY_LEVELS
from ezo_api.settings import API_DIR

ROADMAP = (API_DIR.parent.parent / "ROADMAP.md").read_text(encoding="utf-8")


def test_available_agents_are_exactly_the_implemented_ones() -> None:
    available = {spec.key for spec in AGENTS.values() if spec.available}
    assert available == {"general", "research", "document", "presentation", "language_coach"}
    registry = AgentRegistry()
    for spec in AGENTS.values():
        selected = registry.select(spec.intent).agent.spec.key
        # An available agent has a real implementation; a planned one is covered by General.
        assert selected == (spec.key if spec.available else "general")


def test_planned_agents_carry_an_honest_limitation_note() -> None:
    for spec in AGENTS.values():
        assert spec.maturity in MATURITY_LEVELS
        if not spec.available:
            assert spec.maturity == "planned" and spec.limitation_note


def test_phases_exist_in_the_one_roadmap() -> None:
    for phase in {s.phase for s in AGENTS.values()} | {f.phase for f in FEATURES}:
        assert f"### {phase}" in ROADMAP, phase
    assert "Milestone" not in ROADMAP  # the old milestone numbering is gone


def test_feature_keys_are_unique() -> None:
    keys = [f.key for f in FEATURES]
    assert len(keys) == len(set(keys))
