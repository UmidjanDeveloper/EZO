# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""DeveloperAgent: "Menga kafe uchun website tuz", "Python'da kalkulyator dasturi yoz",
"Telegram bot yozib ber" → a complete project the user downloads as a ZIP.

A build request asks the coding route for every file of the project (between markers, see
`ezo_api.developer.project`). EZO checks each path and size, packs the files into a ZIP
artifact and, for a website, also stores the page with its CSS and JS inlined (one file that
opens in any browser, shown as a preview in EZO). A follow-up ("tugmani ko'k qil", "kirish
sahifasini qo'sh") changes the latest project of the conversation and saves a new version.

EZO never runs the generated code and says so. Questions about code (debugging, explaining)
are answered normally on the coding route.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.general import GeneralAgent
from ezo_api.agents.llm import complete
from ezo_api.agents.references import latest_artifact
from ezo_api.artifacts.service import ArtifactError
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.developer.project import (
    Project,
    ProjectError,
    bundle_site,
    deleted_paths,
    from_zip,
    merge,
    parse_project,
    to_zip,
)
from ezo_api.developer.requests import is_build_request
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage
from ezo_api.tools.document_tools import artifact_entry

logger = logging.getLogger(__name__)

TOOL = "build_project"
"""Trace name of a build (listed in EzoCore's ARTIFACT_TOOLS: a failure gets a fixed notice)."""

_NEW = re.compile(r"\b(yangi|boshqa|new|another|новы\w*|друго\w*)\b")
_EDIT = re.compile(
    r"\b(o'zgartir|almashtir|qo'sh|olib tashla|o'chir|tuzat|yaxshila|kattalashtir|kichraytir|"
    r"rangini|rangi|qil(ib ber)?$|change|add|remove|delete|fix|improve|make (it|the)|rename|"
    r"измени|добавь|убери|удали|исправь|сделай (его|её|ее|кнопк|фон))"
)

DEVELOPER_INSTRUCTIONS = """Role: EZO's Developer Agent.
- Help with programming: explain, debug, review and write code. Prefer complete, working examples over fragments.
- You cannot see the user's computer or repository and you cannot run code: never claim code was run or tested. Ask for the exact error message or the relevant file when it is needed.
- When EZO's notes say a project was built, describe it from those notes: what it does, the files, and how to run it step by step (from its README). Do not paste the whole code again; the ZIP card under the message has it.
- Answer in the user's language; code, file names and commands stay as they are."""

BUILD_SYSTEM = """You are EZO's software builder. Build the complete, working project the user asks for.

Output format — follow it exactly:
<<<FILE relative/path.ext>>>
(the full content of the file)
<<<END>>>
Repeat for every file. Outside the markers write at most one short line. No ``` fences.

Rules:
- Write EVERY file needed to run the project, complete: no "..." placeholders, no "rest of the code", no TODOs.
- Always include README.md in the user's language ({language}): what the project does, the files, and exact steps to run it on Windows (PowerShell) and macOS/Linux.
- A website: plain HTML, CSS and JavaScript (index.html, style.css, script.js, more pages if useful) unless the user asks for a framework. It must open by double-clicking index.html: no build step, no server, relative paths only. Modern, responsive, polished design (mobile first, good typography, spacing, accessible colours, semantic HTML, alt texts). Use realistic sample content in the user's language. Images: use inline SVG or CSS gradients, not external photos.
- A program: choose the language the user named (Python 3.11+ by default for scripts, bots and APIs). Include the dependency file (requirements.txt / package.json) with pinned major versions, and a .env.example for any key. Never put real secrets in code; read them from environment variables.
- A Telegram bot: python-telegram-bot v21 (async) or aiogram 3, the token from the BOT_TOKEN environment variable.
- Keep the project small and focused (usually 3–12 files). Code comments in English; user-facing text in the user's language unless they asked otherwise.
- Never include code that harms users or systems, collects credentials deceptively, or hides what it does."""

EDIT_SYSTEM = (
    BUILD_SYSTEM
    + """

You are CHANGING an existing project (its files are given). Output ONLY the files you change or add, each complete (the whole file, not a diff). To delete a file write one line: <<<DELETE relative/path.ext>>>. Keep everything the user did not ask to change. Update README.md if how to run it changed."""
)

PROJECT_CONTEXT_CHARS = 120_000


def wants_build(text: str) -> bool:
    """A request to make a new program, website, bot or app (not a question about code)."""
    return is_build_request(text)


def wants_project_edit(text: str) -> bool:
    """A change request ("tugmani ko'k qil", "add a contact page") for the latest project."""
    return bool(_EDIT.search(normalize(text).strip(" .!?")))


async def latest_project(ctx: GatherContext) -> Any:
    tools = ctx.tools
    artifact = await latest_artifact(tools.session, tools.user_id, tools.conversation_id, ("code",))
    if artifact is None or (artifact.meta or {}).get("action") != "code_project":
        return None
    return artifact


def _title(text: str, project: Project, fallback: str) -> str:
    readme = project.files.get("README.md", "")
    heading = next(
        (line.lstrip("# ").strip() for line in readme.splitlines() if line.startswith("# ")), ""
    )
    title = heading or fallback or " ".join(text.split()[:8])
    return title[:120] or "EZO project"


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize(title)).strip("-")
    return (slug or "ezo-project")[:48]


def _project_listing(files: dict[str, str]) -> str:
    out: list[str] = []
    used = 0
    for path, content in files.items():
        block = f"<<<FILE {path}>>>\n{content}<<<END>>>\n"
        if used + len(block) > PROJECT_CONTEXT_CHARS:
            out.append(f"(file {path} omitted: the project is too large to show in full)")
            continue
        out.append(block)
        used += len(block)
    return "\n".join(out)


class DeveloperAgent(Agent):
    spec = AGENTS[Intent.DEVELOPER]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="coding",
            context_mode="technical",
            instructions=DEVELOPER_INSTRUCTIONS,
            steps=("detect_build", "build_project", "compose_prompt", "generate", "verify"),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        text = ctx.turn.text
        previous = await latest_project(ctx)
        building = wants_build(text)
        editing = (
            previous is not None
            and not (building and _NEW.search(normalize(text)))
            and (wants_project_edit(text) or building)
        )
        if not building and not editing:
            # A question: look into the user's files like the general companion does (their
            # code or notes may hold the answer), plus the latest project when there is one.
            gathered = await GeneralAgent().gather(ctx)
            if previous is not None:
                await self._share_project(ctx, gathered, previous)
            return gathered
        if ctx.tools.services.router.is_offline:
            gathered.notes.append(
                "No AI provider is connected, so EZO cannot write the project now. Say so briefly."
            )
            gathered.tool_calls.append(
                {"tool": TOOL, "ok": False, "summary": "offline", "error": "no AI provider"}
            )
            return gathered
        await self._build(ctx, gathered, previous if editing else None)
        return gathered

    async def _share_project(self, ctx: GatherContext, gathered: Gathered, artifact: Any) -> None:
        """A question about the latest project: give the model its files to answer from."""
        tools = ctx.tools
        version = await tools.services.artifacts.current_version(tools.session, artifact)
        if version is None:
            return
        files = from_zip(await tools.services.artifacts.read(version))
        gathered.notes.append(
            f"The conversation's latest project is “{artifact.title}” (v{version.version_number}). "
            "Its files follow; answer questions about it from them. To change it the user can "
            "simply ask (e.g. “add a contact page”).\n" + _project_listing(files)
        )

    async def _build(self, ctx: GatherContext, gathered: Gathered, previous: Any) -> None:
        tools = ctx.tools
        services = tools.services
        language = ctx.turn.language
        old_files: dict[str, str] = {}
        version = None
        if previous is not None:
            version = await services.artifacts.current_version(tools.session, previous)
            if version is not None:
                old_files = from_zip(await services.artifacts.read(version))
        if tools.on_activity is not None:
            tools.on_activity("working")
        request = text = ctx.turn.text
        if ctx.history_hint and not wants_build(text):
            request = f"Earlier request: {ctx.history_hint}\nNow: {text}"
        prompt = (
            f"The current project files:\n{_project_listing(old_files)}\n\nChange request: {request}"
            if old_files
            else f"Build this: {request}"
        )
        system = (EDIT_SYSTEM if old_files else BUILD_SYSTEM).replace("{language}", language)
        try:
            completion = await complete(
                services.router,
                "coding",
                system=system,
                messages=[ChatMessage("user", prompt)],
                max_output_tokens=32_000,
                language=language,
            )
        except (AllProvidersFailedError, StreamInterruptedError) as exc:
            logger.warning("Project build failed: %s", exc)
            gathered.tool_calls.append(
                {
                    "tool": TOOL,
                    "ok": False,
                    "summary": "model failed",
                    "error": "the AI provider failed",
                }
            )
            gathered.notes.append(
                "Writing the project failed (the AI provider did not answer). Say so and suggest trying again."
            )
            return
        try:
            changed = parse_project(completion.text)
            project = (
                merge(old_files, changed, deleted_paths(completion.text)) if old_files else changed
            )
        except ProjectError as exc:
            gathered.tool_calls.append(
                {"tool": TOOL, "ok": False, "summary": "no files", "error": str(exc)}
            )
            gathered.notes.append(
                "The model did not return usable project files. Say so honestly and offer to try again with a more specific request."
            )
            return
        truncated = completion.finish_reason in ("length", "max_tokens", "MAX_TOKENS")
        if "README.md" not in project.files:
            project.files["README.md"] = f"# {' '.join(text.split()[:8])}\n\nEZO.\n"

        title = previous.title if previous is not None else _title(text, project, "")
        folder = _slug(title)
        exports: dict[str, tuple[str, bytes]] = {}
        site = bundle_site(project)
        if site is not None:
            exports["site"] = (f"{folder}.html", site.encode("utf-8"))
        meta = {
            "kind": "website" if project.is_website else "program",
            "files": [
                {"path": p, "size": len(c.encode("utf-8"))} for p, c in project.files.items()
            ],
            "entry": project.entry_html,
            "skipped": project.skipped,
            "truncated": truncated,
            "executed": False,
        }
        data = to_zip(project, folder)
        try:
            if previous is not None:
                created = await services.artifacts.add_version(
                    tools.session,
                    previous,
                    filename=f"{folder}.zip",
                    data=data,
                    created_by="agent:developer",
                    provider=completion.provider,
                    model=completion.model,
                    generation_metadata=meta,
                    change_summary=" ".join(text.split())[:200],
                    exports=exports,
                )
            else:
                created = await services.artifacts.create(
                    tools.session,
                    tools.user_id,
                    title=title,
                    artifact_type="code",
                    filename=f"{folder}.zip",
                    data=data,
                    project_id=tools.project_scope,
                    conversation_id=tools.conversation_id,
                    created_by_agent="developer",
                    provider=completion.provider,
                    model=completion.model,
                    metadata={"action": "code_project", "kind": meta["kind"]},
                    generation_metadata=meta,
                    exports=exports,
                )
        except ArtifactError as exc:
            gathered.tool_calls.append(
                {"tool": TOOL, "ok": False, "summary": "store failed", "error": exc.message}
            )
            return
        gathered.artifacts.append(artifact_entry(created))
        listing = ", ".join(project.files)
        gathered.tool_calls.append(
            {
                "tool": TOOL,
                "ok": True,
                "summary": f"{len(project.files)} files ({'edit' if old_files else 'new'})",
                "error": None,
            }
        )
        lines = [
            (
                f"EZO changed the project “{title}” and saved version v{created.version.version_number}: "
                f"changed or added {', '.join(changed.files)}."
                if old_files
                else f"EZO built the project “{title}”: {len(project.files)} files ({listing}), saved as a ZIP (card under the message)."
            ),
            "It is a website: the card also has a one-file version (open it in any browser) and a preview."
            if site is not None
            else "It is a program: the README explains how to install and run it.",
            "EZO did NOT run or test the code: say so in one short line and ask the user to tell you any error they see.",
            "README (for the run steps; summarise, do not paste):\n"
            + project.files["README.md"][:4_000],
        ]
        if project.skipped:
            lines.append(
                f"Files refused as unsafe or unsupported (not saved): {', '.join(project.skipped[:10])}."
            )
        if truncated:
            lines.append(
                "The model's answer was cut off, so the project may be incomplete: say so and offer to continue (“davom et”)."
            )
        gathered.notes.append("\n".join(lines))
