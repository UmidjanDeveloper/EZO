"""Bounded decimal arithmetic for inspectable multi-step tasks.

Adapts EasyTool/FuncQA's explicit arithmetic-tool approach, not its float-based
rounding or unrestricted function catalog. Reference: microsoft/JARVIS at
7624cf388b47334ff8a0868e7d862dde18cfda86, easytool/data_funcqa/funchub/math.py.
No upstream implementation or benchmark dataset is copied here.
"""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ezo_api.tools.base import Tool, ToolContext, ToolResult

NUMBER = r"^-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?$"


class PercentagePair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    previous: str = Field(strict=True, max_length=32, pattern=NUMBER)
    current: str = Field(strict=True, max_length=32, pattern=NUMBER)


class PercentageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["percent_change", "percent_of"]
    pairs: list[PercentagePair] = Field(min_length=1, max_length=50)
    decimal_places: int = Field(default=4, ge=0, le=8, strict=True)


def calculate_percentages(args: PercentageArgs) -> dict[str, Any]:
    if len({p.id for p in args.pairs}) != len(args.pairs):
        raise ValueError("Pair identifiers must be unique.")
    if any(Decimal(p.previous) == 0 for p in args.pairs):
        raise ValueError("Previous value must be nonzero; percentage is undefined.")
    results: list[dict[str, str]] = []
    with localcontext() as ctx:
        ctx.prec = 64
        unit = Decimal(1).scaleb(-args.decimal_places)
        for pair in args.pairs:
            previous, current = Decimal(pair.previous), Decimal(pair.current)
            numerator = current - previous if args.method == "percent_change" else current
            value = (numerator / previous * 100).quantize(unit, rounding=ROUND_HALF_EVEN)
            if value == 0:
                value = abs(value)
            results.append(
                {
                    "id": pair.id,
                    "previous": pair.previous,
                    "current": pair.current,
                    "result_percent": format(value, "f"),
                }
            )
    return {
        "method": args.method,
        "formula": "(current-previous)/previous*100"
        if args.method == "percent_change"
        else "current/previous*100",
        "rounding": "ROUND_HALF_EVEN",
        "decimal_places": args.decimal_places,
        "provenance": "caller_supplied_values_not_document_extraction",
        "results": results,
    }


class PercentageTool(Tool[PercentageArgs]):
    name: ClassVar[str] = "calculate_percentages"
    description: ClassVar[str] = (
        "Calculate explicit percent_change or percent_of using bounded decimal strings. "
        "Ask which method is intended; never infer extracted document values."
    )
    args_model: ClassVar[type[BaseModel]] = PercentageArgs
    timeout_seconds: ClassVar[float] = 2

    async def run(self, args: PercentageArgs, ctx: ToolContext) -> ToolResult:
        try:
            result = calculate_percentages(args)
        except ValueError as exc:
            return ToolResult(ok=False, summary="Percentage calculation rejected.", error=str(exc))
        return ToolResult(ok=True, summary="Decimal percentages calculated.", data=result)
