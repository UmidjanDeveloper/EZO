"""Verify global code-point coordinates, including unambiguous legacy text chunks."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import DocumentRevision, KnowledgeChunk


async def chunk_offsets(session: AsyncSession, chunk: KnowledgeChunk) -> tuple[int, int] | None:
    start, end = chunk.meta.get("start"), chunk.meta.get("end")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= 2_000_000:
        exact = await session.scalar(
            select(func.substr(DocumentRevision.raw_text, start + 1, end - start)).where(
                DocumentRevision.id == chunk.revision_id,
                DocumentRevision.document_id == chunk.document_id,
                func.length(DocumentRevision.raw_text) <= 2_000_000,
            )
        )
        return (start, end) if exact == chunk.text else None
    # Do not rewrite legacy revisions or guess positions of repeated passages.
    # SQL scans a bounded prefix; no full source ORM materialization in the API.
    position = (
        func.strpos if session.bind and session.bind.dialect.name == "postgresql" else func.instr
    )
    prefix = func.substr(DocumentRevision.raw_text, 1, 2_000_000)
    first = await session.scalar(
        select(position(prefix, chunk.text)).where(
            DocumentRevision.id == chunk.revision_id,
            DocumentRevision.document_id == chunk.document_id,
            func.length(DocumentRevision.raw_text) <= 2_000_000,
        )
    )
    if not first or not chunk.text:
        return None
    duplicate = await session.scalar(
        select(position(func.substr(prefix, first + 1), chunk.text)).where(
            DocumentRevision.id == chunk.revision_id,
            DocumentRevision.document_id == chunk.document_id,
            func.length(DocumentRevision.raw_text) <= 2_000_000,
        )
    )
    if duplicate:
        return None
    return first - 1, first - 1 + len(chunk.text)
