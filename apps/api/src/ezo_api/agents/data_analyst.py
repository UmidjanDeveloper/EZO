# ruff: noqa: E501
"""DataAnalystAgent: "Shu Excel'ni tahlil qil", "Trend va prognoz chiqar", "Grafik chiz".

Every number comes from `ezo_api.analytics.stats` (computed, never guessed). The workbook is
never opened in the API: CSV is read as text, XLSX from the text the isolated document worker
extracted. The result is an Excel file EZO writes itself, with native charts.
"""

from __future__ import annotations

import asyncio
import hashlib
import re

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.office import attached_files, recent_files
from ezo_api.analytics.report import render
from ezo_api.analytics.stats import analyse, as_notes
from ezo_api.analytics.table import CSV_MIMES, XLSX_MIME, TableError, load_tables
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.tools.document_tools import artifact_entry

ANALYSE = re.compile(
    r"(tahlil|statistik|trend|tendens|prognoz|bashorat|o'sish|pasay|dinamika|grafik|diagramma|"
    r"o'rtacha|anomal|g'ayrioddiy|korrelyats|analy[sz]|statistic|forecast|chart|graph|average|outlier|"
    r"анализ|проанализ|статистик|тренд|прогноз|динамик|график|диаграмм|средн|аномал|корреляц)"
)
SPREADSHEET_WORDS = re.compile(r"(excel|xlsx|csv|jadval|sheet|spreadsheet|таблиц)")

INSTRUCTIONS = (
    "Role: EZO's data analyst. Explain the analysis using ONLY the exact numbers in EZO's "
    "notes (computed by EZO): the main totals, the trend and its direction, unusual values to "
    "check, group leaders, strong correlations. A forecast is a linear estimate — say so. "
    "Never invent numbers or causes. Mention the Excel file with charts. Answer in the user's "
    "language, briefly, with a short bullet list."
)


def wants_analysis(text: str, has_sheet: bool) -> bool:
    norm = normalize(text)
    return bool(ANALYSE.search(norm)) and (has_sheet or bool(SPREADSHEET_WORDS.search(norm)))


class DataAnalystAgent(Agent):
    spec = AGENTS[Intent.DATA]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="chat",
            context_mode="technical",
            instructions=INSTRUCTIONS,
            steps=("load_table", "compute", "excel_report", "generate"),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        mimes = (XLSX_MIME, *CSV_MIMES)
        files = [
            d for d in await attached_files(tools, ctx.turn.attachments) if d.mime_type in mimes
        ]
        if not files and not ctx.turn.attachments:
            files = await recent_files(tools, mimes, 1)
        if not files:
            gathered.notes.append(
                "No Excel or CSV file was attached (or uploaded recently). Ask the user to attach one."
            )
            return gathered
        document = files[-1]
        try:
            tables = await load_tables(tools.session, tools.services.storage, document)
        except TableError as exc:
            gathered.tool_calls.append(
                {"tool": "analyse_table", "ok": False, "summary": "", "error": exc.message}
            )
            gathered.notes.append(
                f"The table in «{document.title}» could not be read: {exc.message} Say so."
            )
            return gathered
        norm = normalize(ctx.turn.text)
        table = next(
            (t for t in tables if normalize(t.name) and normalize(t.name) in norm), tables[0]
        )
        analysis = await asyncio.to_thread(analyse, table)
        data = await asyncio.to_thread(render, table, analysis)
        stem = (document.title or "jadval").rsplit(".", 1)[0][:80]
        created = await tools.services.artifacts.create(
            tools.session,
            tools.user_id,
            title=f"{stem} — tahlil",
            artifact_type="spreadsheet",
            filename=f"{stem} - tahlil.xlsx",
            data=data,
            project_id=tools.project_scope,
            conversation_id=tools.conversation_id,
            created_by_agent="data_analyst",
            generation_metadata={
                "operation": "data_analysis",
                "table": table.name,
                "rows": analysis.rows,
                "inputs": [{"kind": "document", "id": str(document.id), "title": document.title}],
                "output": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
            },
            change_summary="Created",
        )
        gathered.artifacts.append(artifact_entry(created))
        gathered.tool_calls.append(
            {
                "tool": "analyse_table",
                "ok": True,
                "summary": f"{table.name}: {analysis.rows} rows",
                "error": None,
            }
        )
        other = [t.name for t in tables if t is not table]
        gathered.notes.append(
            "Analysis computed by EZO (use these exact values):\n- "
            + "\n- ".join(as_notes(analysis))
            + (
                f"\n- Other sheets not analysed: {', '.join(other)} (the user can name one)."
                if other
                else ""
            )
            + "\nEZO made an Excel file with the data, a statistics sheet, trend sheets with line charts "
            "(forecast marked as an estimate) and group totals with bar charts."
        )
        return gathered
