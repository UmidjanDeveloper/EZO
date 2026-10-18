# ruff: noqa: E501  (prompt text is kept on readable lines)
"""Long documents in DocumentAgent: the whole text is processed, part by part.

- **Summaries** are map-reduce: every part (cut at the document's own headings) is
  summarised, then the part summaries are combined, in rounds if needed.
- **Translations and rewrites** of non-Word files are done part by part and joined.
- **Questions** about a long file search the whole file and answer from the most
  relevant passages (with their sections).

Every part result is saved (`long_doc_parts`, keyed by the part's content hash) as soon
as it is done. If the AI provider fails half-way, the finished parts are kept and the
next request continues from there. Nothing is cut off silently: the reply always says
how many parts and characters were covered.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ezo_api.agents.base import GatherContext, Gathered
from ezo_api.agents.llm import complete
from ezo_api.db.models import KnowledgeDocument, LongDocPart
from ezo_api.documents.longdoc import MAX_TOTAL_CHARS, Part, split_parts
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage

REDUCE_CHARS = 50_000

PART_SUMMARY_SYSTEM = """You summarize ONE part of a long document for a later combined summary.
Keep every key fact, number, amount, date, name, obligation and deadline exactly as written. Keep the section titles you see. No introduction, no commentary, no facts that are not in the part. Write in {language}. At most about 350 words."""

COMBINE_SYSTEM = """You combine summaries of consecutive parts of ONE document into a single summary of the whole document.
Use headings that follow the document's own sections. Keep every key fact, number, date and name exactly; remove repetition; never add facts. Write in {language}. Start directly with the summary (no preface)."""

PART_TRANSFORM_SYSTEM = """You are EZO's document editor. {task}
You receive ONE part of a long document (part {n} of {total}). Return ONLY the transformed text of this part, in Markdown, keeping its headings, lists and tables. No title of your own, no comments, no "Part" labels. Never add facts; mark unclear places with [?]."""


@dataclass(slots=True)
class PartsRun:
    results: list[str] = field(default_factory=list)
    reused: int = 0
    computed: int = 0
    failed_at: int | None = None
    provider: str | None = None
    model: str | None = None

    @property
    def complete(self) -> bool:
        return self.failed_at is None


async def _cached(ctx: GatherContext, task: str, part: Part) -> str | None:
    tools = ctx.tools
    row = await tools.session.scalar(
        select(LongDocPart).where(
            LongDocPart.user_id == tools.user_id,
            LongDocPart.task == task,
            LongDocPart.part_sha256 == part.sha256,
        )
    )
    return row.result if row is not None else None


async def _save(
    ctx: GatherContext, task: str, part: Part, source_sha: str, result: str, run: PartsRun
) -> None:
    """Saved with the turn (provider failures are caught, so the turn still commits and
    the finished parts survive for the next request)."""
    session = ctx.tools.session
    try:
        async with session.begin_nested():
            session.add(
                LongDocPart(
                    user_id=ctx.tools.user_id,
                    task=task[:120],
                    part_sha256=part.sha256,
                    source_sha256=source_sha,
                    part_index=part.index,
                    result=result,
                    provider=run.provider,
                    model=run.model,
                )
            )
    except IntegrityError:  # the same part was saved by a concurrent request
        pass


async def run_parts(
    ctx: GatherContext,
    gathered: Gathered,
    parts: list[Part],
    *,
    task: str,
    system_for: Callable[[Part], str],
    prompt_for: Callable[[Part], str],
    max_tokens_for: Callable[[Part], int],
    source_sha: str,
) -> PartsRun:
    """Run one model call per part (skipping parts already done) in document order."""
    run = PartsRun()
    tools = ctx.tools
    for part in parts:
        cached = await _cached(ctx, task, part)
        if cached is not None:
            run.results.append(cached)
            run.reused += 1
            continue
        if tools.on_activity is not None:
            tools.on_activity("reading")
        try:
            completion = await complete(
                tools.services.router,
                "chat",
                system=system_for(part),
                messages=[ChatMessage("user", prompt_for(part))],
                max_output_tokens=max_tokens_for(part),
                language=ctx.turn.language,
            )
        except (AllProvidersFailedError, StreamInterruptedError):
            run.failed_at = part.index
            return run
        run.provider, run.model = completion.provider, completion.model
        gathered.tool_calls.append(completion.trace(f"{task.split(':')[0]}_part", part.label))
        text = completion.text.strip()
        run.results.append(text)
        run.computed += 1
        await _save(ctx, task, part, source_sha, text, run)
    return run


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class LongSummary:
    text: str
    parts: int
    chars: int
    reused: int
    rounds: int
    provider: str | None
    model: str | None


async def summarize_long(
    ctx: GatherContext, gathered: Gathered, title: str, text: str, language: str
) -> LongSummary | None:
    """Map-reduce summary of the whole text; None (with a note) when it could not finish."""
    parts = split_parts(text)
    sha = source_hash(text)
    run = await run_parts(
        ctx,
        gathered,
        parts,
        task=f"summary:{language}",
        system_for=lambda _p: PART_SUMMARY_SYSTEM.replace("{language}", language),
        prompt_for=lambda p: (
            f"Document “{title}”, part {p.index + 1} of {len(parts)} ({p.label}):\n\n{p.text}"
        ),
        max_tokens_for=lambda _p: 900,
        source_sha=sha,
    )
    if not run.complete:
        gathered.notes.append(
            f"The summary of “{title}” stopped after {run.failed_at} of {len(parts)} parts because "
            "the AI provider failed. The finished parts are saved: asking again continues from "
            "where it stopped. Say this plainly; do not present a partial summary as complete."
        )
        return None
    summaries = [f"## {p.label}\n{s}" for p, s in zip(parts, run.results, strict=True)]
    rounds = 1
    combined = "\n\n".join(summaries)
    while len(combined) > REDUCE_CHARS and len(summaries) > 1:
        rounds += 1
        groups = [
            Part(i, "\n\n".join(summaries[j : j + 6]), ())
            for i, j in enumerate(range(0, len(summaries), 6))
        ]
        reduced = await run_parts(
            ctx,
            gathered,
            groups,
            task=f"summary-combine:{language}",
            system_for=lambda _p: COMBINE_SYSTEM.replace("{language}", language),
            prompt_for=lambda p: f"Document “{title}”: summaries of consecutive parts:\n\n{p.text}",
            max_tokens_for=lambda _p: 1_500,
            source_sha=sha,
        )
        if not reduced.complete:
            gathered.notes.append(
                f"Combining the part summaries of “{title}” failed (AI provider). The part "
                "summaries are saved; asking again continues. Say so plainly."
            )
            return None
        summaries = reduced.results
        combined = "\n\n".join(summaries)
    tools = ctx.tools
    try:
        final = await complete(
            tools.services.router,
            "chat",
            system=COMBINE_SYSTEM.replace("{language}", language),
            messages=[
                ChatMessage(
                    "user",
                    f"User's request: {ctx.turn.text}\n\nDocument “{title}” ({len(parts)} parts, "
                    f"{len(text):,} characters). Part summaries in order:\n\n{combined}",
                )
            ],
            max_output_tokens=4_000,
            language=ctx.turn.language,
        )
    except (AllProvidersFailedError, StreamInterruptedError):
        gathered.notes.append(
            f"The final summary of “{title}” could not be written (AI provider failed); all "
            f"{len(parts)} part summaries are saved, so asking again is quick. Say so plainly."
        )
        return None
    gathered.tool_calls.append(final.trace("combine_summary", f"{len(parts)} parts"))
    return LongSummary(
        final.text.strip(),
        len(parts),
        len(text),
        run.reused,
        rounds,
        final.provider,
        final.model,
    )


async def transform_long(
    ctx: GatherContext,
    gathered: Gathered,
    title: str,
    text: str,
    *,
    transform: str,
    task: str,
    task_key: str,
) -> tuple[str, PartsRun, int] | None:
    """(markdown, run, parts) of the whole text transformed part by part; None when the
    provider failed (finished parts are kept for the next request)."""
    parts = split_parts(text)
    run = await run_parts(
        ctx,
        gathered,
        parts,
        task=task_key,
        system_for=lambda p: (
            PART_TRANSFORM_SYSTEM.replace("{task}", task)
            .replace("{n}", str(p.index + 1))
            .replace("{total}", str(len(parts)))
        ),
        prompt_for=lambda p: (
            f"User's request: {ctx.turn.text}\n\nPart {p.index + 1} of "
            f"{len(parts)} of “{title}”:\n\n{p.text}"
        ),
        max_tokens_for=lambda p: min(16_000, int(len(p.text) / 2) + 1_500),
        source_sha=source_hash(text),
    )
    if not run.complete:
        gathered.notes.append(
            f"The {transform} of “{title}” stopped after {run.failed_at} of {len(parts)} parts "
            "because the AI provider failed. Nothing was saved as a document yet; the finished "
            "parts are kept, and asking again continues from where it stopped. Say so plainly."
        )
        return None
    return "\n\n".join(r for r in run.results if r), run, len(parts)


def too_long_note(title: str, chars: int) -> str:
    return (
        f"“{title}” has {chars:,} characters, more than EZO processes in one request "
        f"({MAX_TOTAL_CHARS:,}). Nothing was cut off and nothing was saved. Suggest naming "
        "the chapters or pages to work on, or splitting the file."
    )


async def answer_sources(
    ctx: GatherContext, document: KnowledgeDocument, question: str, limit: int = 8
) -> list[SourceRef]:
    """The most relevant passages of one (long) document for a question."""
    tools = ctx.tools
    result = await tools.services.retriever.retrieve(
        tools.session,
        tools.user_id,
        question[:500],
        tools.project_scope,
        limit=limit,
        document_ids=frozenset({document.id}),
    )
    gathered_sources = list(result.sources)
    for number, source in enumerate(gathered_sources, start=1):
        source.n = number
    return gathered_sources
