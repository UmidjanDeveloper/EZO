"""Tools used by the ResearchAgent (and available to future agents)."""

from __future__ import annotations

import asyncio
import uuid
from typing import ClassVar

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ezo_api.knowledge.fetch import FetchError
from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.parsers import ParseError, parse
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.learning.service import resolve_library_documents
from ezo_api.tools.base import Tool, ToolContext, ToolResult
from ezo_api.tools.reliability import score_url
from ezo_api.tools.web_search import WebSearchError

FETCH_EXCERPT_CHARS = 4_000


class KnowledgeSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)
    strict: bool = Field(default=False, description="Only clearly relevant passages")
    library_id: uuid.UUID | None = Field(
        default=None,
        description="Optional knowledge library ID to scope retrieval to.",
    )


class KnowledgeSearchTool(Tool[KnowledgeSearchArgs]):
    name: ClassVar[str] = "knowledge_search"
    activity: ClassVar[str] = "searching"
    description: ClassVar[str] = "Search the user's uploaded files and saved web pages."
    args_model: ClassVar[type[BaseModel]] = KnowledgeSearchArgs

    async def run(self, args: KnowledgeSearchArgs, ctx: ToolContext) -> ToolResult:
        target_library_id = args.library_id or ctx.library_scope
        document_ids: frozenset[uuid.UUID] | None = None

        if target_library_id is not None:
            try:
                _lib, doc_ids = await resolve_library_documents(
                    ctx.session,
                    user_id=ctx.user_id,
                    library_id=target_library_id,
                )
                document_ids = doc_ids
            except HTTPException as exc:
                return ToolResult(
                    ok=False,
                    summary=f"Library access denied: {exc.detail}",
                    error=str(exc.detail),
                    sources=[],
                )

        result = await ctx.services.retriever.retrieve(
            ctx.session,
            ctx.user_id,
            args.query,
            ctx.project_scope,
            document_ids=document_ids,
            limit=args.limit,
            strict=args.strict,
        )
        return ToolResult(
            ok=True,
            summary=f"{len(result.sources)} passages ({result.mode})",
            data=result.diagnostics,
            sources=result.sources,
        )


class WebSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=5, ge=1, le=10)
    recent: bool = False


class WebSearchTool(Tool[WebSearchArgs]):
    name: ClassVar[str] = "web_search"
    activity: ClassVar[str] = "searching"
    description: ClassVar[str] = "Search the web for current information."
    args_model: ClassVar[type[BaseModel]] = WebSearchArgs
    timeout_seconds: ClassVar[float] = 60.0

    async def run(self, args: WebSearchArgs, ctx: ToolContext) -> ToolResult:
        provider = ctx.services.web_search
        if provider is None:
            return ToolResult(ok=False, summary="", error="Web search is not configured.")
        try:
            results = await provider.search(args.query, args.max_results, args.recent)
        except WebSearchError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        sources: list[SourceRef] = []
        for item in results:
            reliability, primary, tier = score_url(item.url)
            sources.append(
                SourceRef(
                    kind="web",
                    title=item.title,
                    excerpt=item.snippet,
                    source_name=tier,
                    url=item.url,
                    date=item.published,
                    reliability=reliability,
                    primary=primary,
                    extra={"provider": item.provider},
                )
            )
        return ToolResult(
            ok=True, summary=f"{len(sources)} results via {provider.name}", sources=sources
        )


class WebFetchArgs(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class WebFetchTool(Tool[WebFetchArgs]):
    name: ClassVar[str] = "web_fetch"
    activity: ClassVar[str] = "reading"
    description: ClassVar[str] = "Open a public web page (http/https) and read its main text."
    args_model: ClassVar[type[BaseModel]] = WebFetchArgs

    async def run(self, args: WebFetchArgs, ctx: ToolContext) -> ToolResult:
        try:
            page = await ctx.services.fetcher.fetch(args.url, respect_robots=True)
        except FetchError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        category = (
            "pdf"
            if page.content_type == "application/pdf"
            else "html"
            if "html" in page.content_type
            else "text"
        )
        try:
            parsed = await asyncio.to_thread(parse, category, page.data, "page")
        except ParseError as exc:
            return ToolResult(ok=False, summary="", error=exc.message)
        text = normalize_text(parsed.text)[:FETCH_EXCERPT_CHARS]
        reliability, primary, tier = score_url(page.final_url)
        source = SourceRef(
            kind="web_page",
            title=parsed.title or page.final_url,
            excerpt=text,
            source_name=str(parsed.metadata.get("sitename") or tier),
            url=page.final_url,
            date=parsed.metadata.get("date"),
            reliability=reliability,
            primary=primary,
        )
        return ToolResult(ok=True, summary=f"{len(text)} characters", sources=[source])
