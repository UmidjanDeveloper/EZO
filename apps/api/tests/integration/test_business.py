"""Business agent: EZO computes the unit economics; market numbers only from cited sources."""

from __future__ import annotations

import io
import json

from docx import Document
from httpx import AsyncClient

from ezo_api.business.economics import Inputs, compute
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


def test_unit_economics_are_computed() -> None:
    facts = compute(
        Inputs(price=25_000, variable_cost=12_000, fixed_costs_month=2_600_000,
               units_per_month=300, startup_cost=15_000_000)
    )  # fmt: skip
    assert facts[0] == "Contribution margin per unit: 13 000 so'm (52.0% of the price)"
    assert facts[1].startswith("Break-even: 200 units per month")
    assert facts[2] == "At 300 units/month: revenue 7 500 000 so'm, profit 1 300 000 so'm per month"
    assert facts[3] == "Payback of the start-up cost 15 000 000 so'm: 11.5 months"
    assert compute(Inputs(price=10, variable_cost=12, fixed_costs_month=5))[1].startswith(
        "No break-even"
    )
    assert compute(Inputs(price=10)) == []
    assert (
        Inputs.from_json({"price": "abc", "variable_cost": -5, "units_per_month": True}) == Inputs()
    )


async def test_chat_business_plan_with_computed_numbers(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    numbers = {
        "price": 25000, "variable_cost": 12000, "fixed_costs_month": 2600000,
        "units_per_month": 300, "startup_cost": 15000000, "currency": "so'm",
        "search_queries": ["Toshkent nonvoyxona bozori"],
    }  # fmt: skip
    fake_anthropic.replies = [
        json.dumps(numbers),
        "# Biznes reja\n\n## Unit iqtisodiyot\n\nMarja 13 000 so'm [Hisob].",
        "Xulosa: loyiha 200 dona/oyda zararsizlikka chiqadi [Hisob].",
    ]
    events = await stream_chat(
        client,
        message="Nonvoyxona uchun biznes reja tuz: narxi 25 ming, tannarxi 12 ming, oyiga 300 ta, "
        "ijara va oylik 2,6 mln, boshlang'ich xarajat 15 mln",
    )
    assert events[0][1]["agent"] == "business"
    system = fake_anthropic.requests[-1].system or ""
    assert "Break-even: 200 units per month" in system
    assert "«[Hisob]»" in system and "Never invent market statistics" in system
    [artifact] = events[-1][1]["message"]["metadata"]["artifacts"]
    data = (await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")).content
    assert "Marja 13 000 so'm" in "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
