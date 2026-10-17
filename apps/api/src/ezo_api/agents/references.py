"""Find the files a request refers to ("shu PDF", "report.docx", "the presentation above").

Only the user's own files are considered, within the conversation's project scope
(project files plus files outside any project), exactly like knowledge search.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.text import normalize
from ezo_api.db.models import Artifact, DocumentRevision, KnowledgeDocument
from ezo_api.knowledge.retrieval.keyword import SEARCHABLE_STATUSES
from ezo_api.knowledge.retrieval.sources import SourceRef

RECENT_DOCUMENTS = 50
_DEICTIC = re.compile(
    r"\b(shu|bu|ushbu|mana|yuqoridagi|yuklagan|yuklangan|biriktirilgan|asosida|this|that|"
    r"these|attached|uploaded|above|based on|этот|эту|этого|этой|данн|загруженн|прикреплённ|"
    r"на основе|выше)\b"
)
_KIND_WORDS: dict[str, tuple[str, ...]] = {
    "pdf": (".pdf",),
    "word": (".docx", ".doc"),
    "docx": (".docx", ".doc"),
    "excel": (".xlsx", ".xls", ".csv"),
    "xlsx": (".xlsx", ".xls"),
    "csv": (".csv",),
    "jadval": (".xlsx", ".xls", ".csv"),
    "spreadsheet": (".xlsx", ".xls", ".csv"),
    "таблиц": (".xlsx", ".xls", ".csv"),
    "rasm": (".png", ".jpg", ".jpeg", ".webp"),
    "image": (".png", ".jpg", ".jpeg", ".webp"),
    "скан": (".png", ".jpg", ".jpeg", ".webp", ".pdf"),
}


@dataclass(frozen=True, slots=True)
class DocumentRef:
    document: KnowledgeDocument
    matched_by: str
    """How it was found: "name" (mentioned by name) or "recent" (the latest matching upload)."""


def _filename_stem(name: str) -> str:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return normalize(stem.replace("_", " ").replace("-", " "))


def wanted_extensions(text: str) -> tuple[str, ...]:
    norm = normalize(text)
    found: list[str] = []
    for word, extensions in _KIND_WORDS.items():
        if re.search(rf"\b{re.escape(word)}", norm):
            found.extend(e for e in extensions if e not in found)
    return tuple(found)


def refers_to_a_file(text: str) -> bool:
    return bool(_DEICTIC.search(normalize(text)))


async def recent_documents(
    session: AsyncSession, user_id: uuid.UUID, project_scope: uuid.UUID | None
) -> list[KnowledgeDocument]:
    return list(
        (
            await session.scalars(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.user_id == user_id,
                    KnowledgeDocument.status.in_(SEARCHABLE_STATUSES),
                    or_(
                        KnowledgeDocument.project_id.is_(None),
                        KnowledgeDocument.project_id == project_scope,
                    ),
                )
                .order_by(KnowledgeDocument.created_at.desc())
                .limit(RECENT_DOCUMENTS)
            )
        ).all()
    )


async def find_documents(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_scope: uuid.UUID | None,
    text: str,
    *,
    limit: int = 1,
) -> list[DocumentRef]:
    """Documents the request names, else (for "this file" style requests) the latest uploads."""
    documents = await recent_documents(session, user_id, project_scope)
    if not documents:
        return []
    norm = normalize(text.replace("_", " ").replace("-", " "))
    named: list[DocumentRef] = []
    for document in documents:
        for name in (document.filename or "", document.title):
            stem = _filename_stem(name)
            if len(stem) >= 4 and stem in norm:
                named.append(DocumentRef(document, "name"))
                break
    if named:
        return named[:limit]
    if not refers_to_a_file(text):
        return []
    extensions = wanted_extensions(text)
    matching = [d for d in documents if (d.filename or "").lower().endswith(extensions)]
    # A format word may name the target ("PDF ga aylantir"), not the source: fall back to
    # the newest uploads when no file has that type.
    matching = matching if extensions and matching else documents
    return [DocumentRef(d, "recent") for d in matching[:limit]]


async def document_text(session: AsyncSession, document: KnowledgeDocument) -> str:
    """The extracted text of the document's current revision."""
    if document.current_revision_id is None:
        return ""
    revision = await session.get(DocumentRevision, document.current_revision_id)
    return revision.raw_text if revision else ""


async def latest_artifact(
    session: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    types: tuple[str, ...],
) -> Artifact | None:
    """The newest artifact of these types created in this conversation."""
    if conversation_id is None:
        return None
    return await session.scalar(
        select(Artifact)
        .where(
            Artifact.user_id == user_id,
            Artifact.conversation_id == conversation_id,
            Artifact.artifact_type.in_(types),
            Artifact.current_version_id.is_not(None),
        )
        .order_by(Artifact.updated_at.desc())
        .limit(1)
    )


def document_source(document: KnowledgeDocument, text: str, limit: int) -> SourceRef:
    """A whole (or the start of a) document as one citable source."""
    return SourceRef(
        kind="file",
        title=document.title,
        excerpt=text[:limit],
        source_name=document.filename or document.title,
        date=document.indexed_at.date().isoformat() if document.indexed_at else None,
        document_id=document.id,
        revision_id=document.current_revision_id,
        reliability=0.9,
        extra={"truncated": len(text) > limit, "chars": len(text)},
    )
