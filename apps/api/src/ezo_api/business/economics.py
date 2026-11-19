# ruff: noqa: E501
"""Unit economics EZO computes itself from the owner's own numbers (never guessed)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Inputs:
    price: float | None = None
    variable_cost: float | None = None
    fixed_costs_month: float | None = None
    units_per_month: float | None = None
    startup_cost: float | None = None
    currency: str = "so'm"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Inputs:
        def num(key: str) -> float | None:
            value = data.get(key)
            if isinstance(value, bool) or value is None:
                return None
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None
            return number if math.isfinite(number) and number >= 0 else None

        return cls(
            price=num("price"), variable_cost=num("variable_cost"),
            fixed_costs_month=num("fixed_costs_month"), units_per_month=num("units_per_month"),
            startup_cost=num("startup_cost"), currency=str(data.get("currency") or "so'm")[:12],
        )  # fmt: skip


def _fmt(value: float, currency: str) -> str:
    return f"{value:,.0f} {currency}".replace(",", " ")


def compute(i: Inputs) -> list[str]:
    """One computed fact per line; nothing when the owner gave too few numbers."""
    lines: list[str] = []
    c = i.currency
    if i.price is not None and i.variable_cost is not None:
        margin = i.price - i.variable_cost
        lines.append(
            f"Contribution margin per unit: {_fmt(margin, c)} ({margin / i.price * 100:.1f}% of the price)"
            if i.price
            else f"Contribution margin per unit: {_fmt(margin, c)}"
        )
        if i.fixed_costs_month is not None:
            if margin > 0:
                breakeven = math.ceil(i.fixed_costs_month / margin)
                lines.append(
                    f"Break-even: {breakeven} units per month (fixed costs {_fmt(i.fixed_costs_month, c)} ÷ margin)"
                )
            else:
                lines.append("No break-even: each unit loses money (price ≤ variable cost).")
        if i.units_per_month is not None:
            revenue = i.price * i.units_per_month
            profit = margin * i.units_per_month - (i.fixed_costs_month or 0)
            lines.append(
                f"At {i.units_per_month:g} units/month: revenue {_fmt(revenue, c)}, profit {_fmt(profit, c)} per month"
            )
            if i.startup_cost is not None:
                if profit > 0:
                    lines.append(
                        f"Payback of the start-up cost {_fmt(i.startup_cost, c)}: {i.startup_cost / profit:.1f} months"
                    )
                else:
                    lines.append(
                        "The start-up cost is not paid back at this volume (no monthly profit)."
                    )
    return lines
