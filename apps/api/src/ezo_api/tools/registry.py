"""ToolRegistry: the only way a tool runs."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from ezo_api.db.models import ToolCall
from ezo_api.documents.isolation import ISOLATION_MESSAGE, native_fixtures_allowed
from ezo_api.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

# These tools can parse/render native formats or load uploaded images/spreadsheets.
ISOLATED_TOOLS = frozenset(
    {
        "pdf_tool",
        "ocr_tool",
        "ocr_export",
        "extract_tables",
        "sheet_ops",
        "office_pdf",
        # create_document / create_spreadsheet / create_presentation are NOT here: they
        # build new files from model text with EZO's own Python renderers (no OCR/Office
        # binaries, no untrusted input parsing), exactly like the REST Office routes that
        # already run in production (audit F19). Presentation images from other artifacts
        # are dropped outside a verified workload (see CreatePresentationTool).
        "create_graphic",
        "edit_image",
        "generate_image",
        "read_document",
        "verify_official_document",
    }
)
MAX_ARG_CHARS = 500
MAX_SUMMARY_CHARS = 1_000
_SECRET_KEYS = ("key", "token", "password", "secret", "authorization", "cookie")


def redact(arguments: dict[str, Any]) -> dict[str, Any]:
    """Arguments safe to store: secrets removed, long strings shortened."""
    safe: dict[str, Any] = {}
    for key, value in arguments.items():
        if any(marker in key.lower() for marker in _SECRET_KEYS):
            safe[key] = "[redacted]"
        elif isinstance(value, str) and len(value) > MAX_ARG_CHARS:
            safe[key] = value[:MAX_ARG_CHARS] + "…"
        elif isinstance(value, str | int | float | bool) or value is None:
            safe[key] = value
        else:
            safe[key] = str(value)[:MAX_ARG_CHARS]
    return safe


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool[Any]] = ()) -> None:
        self._tools: dict[str, Tool[Any]] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(
            name for name in self._tools if native_fixtures_allowed() or name not in ISOLATED_TOOLS
        )

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    async def execute(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.perf_counter()
        tool = self._tools.get(name)
        if tool is None:
            result = ToolResult(ok=False, summary="", error=f"Unknown tool: {name}")
            status = "denied"
        elif name in ISOLATED_TOOLS and not native_fixtures_allowed():
            result = ToolResult(ok=False, summary="", error=ISOLATION_MESSAGE)
            status = "denied"
        elif tool.dangerous and not ctx.allow_dangerous:
            result = ToolResult(ok=False, summary="", error="This action needs your confirmation.")
            status = "denied"
        else:
            try:
                args = tool.args_model.model_validate(arguments)
                if ctx.on_activity is not None:
                    ctx.on_activity(tool.activity)
                result = await asyncio.wait_for(tool.run(args, ctx), tool.timeout_seconds)
                status = "ok" if result.ok else "error"
            except ValidationError as exc:
                result = ToolResult(
                    ok=False, summary="", error=f"Invalid arguments: {exc.errors()[:3]}"
                )
                status = "error"
            except TimeoutError:
                result = ToolResult(ok=False, summary="", error="The tool took too long.")
                status = "error"
            except Exception as exc:
                logger.error("Tool %s crashed (%s)", name, type(exc).__name__)
                result = ToolResult(
                    ok=False, summary="", error=f"Tool failed: {type(exc).__name__}"
                )
                status = "error"

        duration = int((time.perf_counter() - started) * 1000)
        ctx.session.add(
            ToolCall(
                user_id=ctx.user_id,
                agent_run_id=ctx.run_id,
                tool_name=name,
                arguments=redact(arguments),
                status=status,
                result_summary=(result.summary or "")[:MAX_SUMMARY_CHARS] or None,
                error=result.error,
                duration_ms=duration,
            )
        )
        await ctx.session.flush()
        logger.info("tool=%s status=%s duration_ms=%s", name, status, duration)
        return result
