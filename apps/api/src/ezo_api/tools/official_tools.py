"""Tools for official legal sources: search the synchronized texts, verify one live.

`official_search` uses the normal hybrid retrieval, restricted to knowledge documents
that hold official texts, in both Uzbek scripts. Every source carries its legal
metadata (number, authority, dates, status and when it was verified) in front of the
excerpt, so the answer can cite it exactly — and only that.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from ezo_api.db.models import LegalDocument, LegalRevision
from ezo_api.knowledge.retrieval.sources import SourceRef
from ezo_api.official.legal_text import query_variants
from ezo_api.official.registry import CONNECTORS
from ezo_api.official.sync import legal_documents_for, official_knowledge_ids
from ezo_api.tools.base import Tool, ToolContext, ToolResult

STATUS_TEXT = {
    "in_force": "in force",
    "amended": "amended",
    "repealed": "REPEALED (no longer in force)",
    "expired": "EXPIRED",
    "not_yet_in_force": "not yet in force",
}


def _day(value: Any) -> str:
    return value.isoformat()[:10] if value is not None else "not stated"


def status_line(legal: LegalDocument) -> str:
    if legal.status_source == "source_text" and legal.status in STATUS_TEXT:
        when = _day(legal.status_verified_at)
        return f"{STATUS_TEXT[legal.status]} (stated by the official source, checked {when})"
    return "not confirmed (the official source does not state it; do not assume it is in force)"


def legal_header(legal: LegalDocument) -> str:
    source = (
        CONNECTORS[legal.connector].policy.name
        if legal.connector in CONNECTORS
        else legal.connector
    )
    retrieved = (
        legal.last_retrieved_at.isoformat(timespec="minutes")
        if legal.last_retrieved_at
        else "never"
    )
    lines = [
        f"Official document: {legal.title}",
        f"Number: {legal.document_number or 'not stated'}",
        f"Type: {legal.document_type or 'not stated'}",
        f"Authority: {legal.authority or 'not stated'}",
        f"Adopted: {_day(legal.adopted_on)}",
        f"Status: {status_line(legal)}",
        f"Language: {legal.language}",
        f"Last retrieved from {source}: {retrieved}",
        f"Official URL: {legal.official_url}",
    ]
    return "\n".join(lines)


def legal_extra(legal: LegalDocument) -> dict[str, Any]:
    return {
        "legal_document_id": str(legal.id),
        "connector": legal.connector,
        "source_doc_id": legal.source_doc_id,
        "document_number": legal.document_number,
        "document_type": legal.document_type,
        "authority": legal.authority,
        "adopted_on": _day(legal.adopted_on) if legal.adopted_on else None,
        "status": legal.status,
        "status_source": legal.status_source,
        "status_verified_at": legal.status_verified_at.isoformat()
        if legal.status_verified_at
        else None,
        "last_retrieved_at": legal.last_retrieved_at.isoformat()
        if legal.last_retrieved_at
        else None,
        "language": legal.language,
    }


class OfficialSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)
    include_outdated: bool = Field(
        default=False, description="Also search repealed/expired acts (history questions)"
    )


class OfficialSearchTool(Tool[OfficialSearchArgs]):
    name: ClassVar[str] = "official_search"
    activity: ClassVar[str] = "searching"
    description: ClassVar[str] = (
        "Search synchronized official legal texts (e.g. LEX.UZ) with their status and dates."
    )
    args_model: ClassVar[type[BaseModel]] = OfficialSearchArgs

    async def run(self, args: OfficialSearchArgs, ctx: ToolContext) -> ToolResult:
        ids = await official_knowledge_ids(
            ctx.session, ctx.user_id, include_outdated=args.include_outdated
        )
        if not ids:
            return ToolResult(ok=False, summary="", error="No official documents are synchronized.")
        found: dict[uuid.UUID | None, SourceRef] = {}
        modes = []
        for query in query_variants(args.query):
            result = await ctx.services.retriever.retrieve(
                ctx.session, ctx.user_id, query, None, limit=args.limit, document_ids=ids
            )
            modes.append(result.mode)
            for source in result.sources:
                key = source.chunk_id or source.document_id
                if key not in found or source.score > found[key].score:
                    found[key] = source
        sources = sorted(found.values(), key=lambda s: s.score, reverse=True)[: args.limit]
        legal = await legal_documents_for(
            ctx.session, ctx.user_id, [s.document_id for s in sources if s.document_id]
        )
        enriched: list[SourceRef] = []
        for source in sources:
            row = legal.get(source.document_id) if source.document_id else None
            if row is None:
                continue
            source.kind = "web_page"
            source.url = row.official_url
            source.primary = True
            source.reliability = 1.0
            source.source_name = (
                f"{CONNECTORS[row.connector].policy.name} (official)"
                if row.connector in CONNECTORS
                else row.connector
            )
            source.date = _day(row.last_retrieved_at) if row.last_retrieved_at else None
            source.excerpt = f"{legal_header(row)}\n---\n{source.excerpt}"
            source.extra = {**source.extra, "legal": legal_extra(row)}
            enriched.append(source)
        return ToolResult(
            ok=True,
            summary=f"{len(enriched)} official passages ({', '.join(sorted(set(modes)))})",
            data={"documents": len({s.document_id for s in enriched})},
            sources=enriched,
        )


class VerifyOfficialArgs(BaseModel):
    legal_document_id: uuid.UUID


class VerifyOfficialDocumentTool(Tool[VerifyOfficialArgs]):
    name: ClassVar[str] = "verify_official_document"
    activity: ClassVar[str] = "reading"
    timeout_seconds: ClassVar[float] = 60.0
    description: ClassVar[str] = (
        "Re-fetch one official document from its source now (robots.txt and rate limits "
        "apply); a changed text is saved as a new revision."
    )
    args_model: ClassVar[type[BaseModel]] = VerifyOfficialArgs

    async def run(self, args: VerifyOfficialArgs, ctx: ToolContext) -> ToolResult:
        legal = await ctx.session.get(LegalDocument, args.legal_document_id)
        if legal is None or legal.user_id != ctx.user_id:
            return ToolResult(ok=False, summary="", error="Unknown official document.")
        check = await ctx.services.official.verify_live(ctx.session, legal)
        data = {
            "state": check.state,
            "checked_at": check.checked_at.isoformat() if check.checked_at else None,
            "last_verified_at": check.last_verified_at.isoformat()
            if check.last_verified_at
            else None,
            "message": check.message,
        }
        return ToolResult(
            ok=check.state in ("verified", "changed"),
            summary=f"{legal.document_number or legal.title[:60]}: {check.state}",
            data=data,
            error=None if check.state in ("verified", "changed") else check.message,
        )


async def revision_texts(ctx: ToolContext, legal: LegalDocument) -> list[tuple[LegalRevision, str]]:
    """All stored revisions of a legal document with their text (oldest first)."""
    from sqlalchemy import select

    from ezo_api.db.models import DocumentRevision

    rows = (
        await ctx.session.scalars(
            select(LegalRevision)
            .where(LegalRevision.legal_document_id == legal.id)
            .order_by(LegalRevision.revision_number)
        )
    ).all()
    result: list[tuple[LegalRevision, str]] = []
    for row in rows:
        text = ""
        if row.knowledge_revision_id:
            revision = await ctx.session.get(DocumentRevision, row.knowledge_revision_id)
            text = revision.raw_text if revision else ""
        result.append((row, text))
    return result
