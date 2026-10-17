"""KnowledgeService: adding, ingesting, re-indexing and deleting documents.

Pipeline for every document:

    FETCH (storage) → PARSE → NORMALIZE → METADATA → VERSION → CHUNK → EMBED → INDEX

Re-uploading a changed file with the same name (or re-adding a changed URL)
creates a new DocumentRevision; older revisions are kept, only the current one
is searchable.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.language import detect_language
from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DocumentRevision,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
)
from ezo_api.knowledge.embeddings.service import EmbeddingError, EmbeddingService
from ezo_api.knowledge.fetch import FetchError, SafeFetcher
from ezo_api.knowledge.ingestion.chunking import chunk_sections
from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.parsers import ParseError, parse
from ezo_api.knowledge.uploads import (
    UploadRejectedError,
    detect_kind,
    extension_of,
    sanitize_filename,
    sha256_hex,
)
from ezo_api.knowledge.vectorstores import VectorRecord, VectorStoreResolver
from ezo_api.storage.base import StorageError, StorageProvider

logger = logging.getLogger(__name__)

UPLOAD_SOURCE_NAME = "My files"
URL_SOURCE_NAME = "Web pages"
_HTML_TYPES = ("text/html", "application/xhtml+xml")


@dataclass(frozen=True, slots=True)
class AddResult:
    document: KnowledgeDocument
    duplicate: bool
    new_revision: bool


class KnowledgeService:
    def __init__(
        self,
        storage: StorageProvider,
        embeddings: EmbeddingService,
        vectors: VectorStoreResolver,
        fetcher: SafeFetcher,
        max_upload_bytes: int,
    ) -> None:
        self.storage = storage
        self.embeddings = embeddings
        self.vectors = vectors
        self.fetcher = fetcher
        self.max_upload_bytes = max_upload_bytes

    # ------------------------------------------------------------------ sources

    async def _source(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        source_type: str,
        name: str,
    ) -> KnowledgeSource:
        statement = select(KnowledgeSource).where(
            KnowledgeSource.user_id == user_id,
            KnowledgeSource.source_type == source_type,
            KnowledgeSource.project_id.is_(None)
            if project_id is None
            else KnowledgeSource.project_id == project_id,
        )
        source = await session.scalar(statement)
        if source is None:
            source = KnowledgeSource(
                user_id=user_id, project_id=project_id, name=name, source_type=source_type, meta={}
            )
            session.add(source)
            await session.flush()
        return source

    # ------------------------------------------------------------------ adding

    async def _duplicate_of(
        self, session: AsyncSession, user_id: uuid.UUID, content_hash: str
    ) -> KnowledgeDocument | None:
        return await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user_id,
                KnowledgeDocument.content_hash == content_hash,
            )
        )

    async def add_upload(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        filename: str,
        data: bytes,
        project_id: uuid.UUID | None = None,
    ) -> AddResult:
        if len(data) > self.max_upload_bytes:
            limit = self.max_upload_bytes // (1024 * 1024)
            raise UploadRejectedError("too_large", f"The file is larger than {limit} MB.")
        safe_name = sanitize_filename(filename)
        kind = detect_kind(safe_name, data)
        content_hash = sha256_hex(data)

        existing = await self._duplicate_of(session, user_id, content_hash)
        if existing is not None:
            return AddResult(existing, duplicate=True, new_revision=False)

        key = f"uploads/{user_id}/{content_hash[:2]}/{content_hash}{extension_of(safe_name)}"
        await self.storage.put(key, data)

        source = await self._source(session, user_id, project_id, "upload", UPLOAD_SOURCE_NAME)
        document = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_id == source.id,
                KnowledgeDocument.filename == safe_name,
            )
        )
        new_revision = document is not None
        if document is None:
            document = KnowledgeDocument(
                user_id=user_id,
                source_id=source.id,
                project_id=project_id,
                title=safe_name.rsplit(".", 1)[0] or safe_name,
                filename=safe_name,
                mime_type=kind.mime_type,
                meta={},
            )
            session.add(document)
        document.storage_key = key
        document.size_bytes = len(data)
        document.content_hash = content_hash
        document.mime_type = kind.mime_type
        document.status = "queued"
        document.error = None
        document.meta = {**(document.meta or {}), "category": kind.category}
        await session.flush()
        return AddResult(document, duplicate=False, new_revision=new_revision)

    async def add_url(
        self, session: AsyncSession, user_id: uuid.UUID, url: str, project_id: uuid.UUID | None
    ) -> AddResult:
        page = await self.fetcher.fetch(url, respect_robots=True)
        if len(page.data) > self.max_upload_bytes:
            raise UploadRejectedError("too_large", "The page is too large.")
        category = (
            "pdf"
            if page.content_type == "application/pdf"
            else "html"
            if page.content_type.startswith(_HTML_TYPES)
            else "text"
        )
        content_hash = sha256_hex(page.data)
        existing = await self._duplicate_of(session, user_id, content_hash)
        if existing is not None:
            return AddResult(existing, duplicate=True, new_revision=False)

        ext = {"pdf": ".pdf", "html": ".html"}.get(category, ".txt")
        key = f"web/{user_id}/{content_hash[:2]}/{content_hash}{ext}"
        await self.storage.put(key, page.data)

        source = await self._source(session, user_id, project_id, "url", URL_SOURCE_NAME)
        document = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_id == source.id, KnowledgeDocument.source_url == url
            )
        )
        new_revision = document is not None
        if document is None:
            document = KnowledgeDocument(
                user_id=user_id,
                source_id=source.id,
                project_id=project_id,
                title=url,
                source_url=url,
                mime_type=page.content_type,
                meta={},
            )
            session.add(document)
        document.storage_key = key
        document.size_bytes = len(page.data)
        document.content_hash = content_hash
        document.mime_type = page.content_type
        document.status = "queued"
        document.error = None
        document.meta = {
            **(document.meta or {}),
            "category": category,
            "final_url": page.final_url,
            "fetched_at": page.fetched_at,
        }
        await session.flush()
        return AddResult(document, duplicate=False, new_revision=new_revision)

    # ------------------------------------------------------------------ ingest

    async def ingest(self, session: AsyncSession, document_id: uuid.UUID) -> KnowledgeDocument:
        """Run the full pipeline for one document. Never raises for content problems:
        the document ends up `indexed`, `partial`, `needs_ocr` or `failed` with a message."""
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:
            raise LookupError(f"Document {document_id} not found")
        document.status = "processing"
        document.error = None
        await session.commit()
        try:
            await self._run_pipeline(session, document)
        except (ParseError, StorageError, UploadRejectedError) as exc:
            await session.rollback()
            document = await self._reload(session, document_id)
            document.status = "failed"
            document.error = getattr(exc, "message", None) or str(exc)
        except Exception:
            logger.exception("Ingestion crashed for document %s", document_id)
            await session.rollback()
            document = await self._reload(session, document_id)
            document.status = "failed"
            document.error = "Unexpected error while reading the file. See the API logs."
        await session.commit()
        return document

    async def _reload(self, session: AsyncSession, document_id: uuid.UUID) -> KnowledgeDocument:
        document = await session.get(KnowledgeDocument, document_id)
        assert document is not None
        return document

    async def _run_pipeline(self, session: AsyncSession, document: KnowledgeDocument) -> None:
        # FETCH
        if not document.storage_key:
            raise StorageError("The document has no stored file.")
        data = await self.storage.get(document.storage_key)

        # PARSE (CPU-bound: off the event loop)
        category = str((document.meta or {}).get("category", "text"))
        parsed = await asyncio.to_thread(parse, category, data, document.filename or "file")

        # NORMALIZE + METADATA
        raw_text = normalize_text(parsed.text)
        better_title = _useful_title(parsed.title)
        if better_title and (document.source_url or category in ("markdown", "docx")):
            document.title = better_title
        document.language = detect_language(raw_text[:5000]) if raw_text else None
        document.meta = {
            **(document.meta or {}),
            **{
                k: v
                for k, v in parsed.metadata.items()
                if isinstance(v, str | int | float | bool | list)
            },
            "chars": len(raw_text),
        }

        # VERSION
        revision = await self._revision_for(session, document, raw_text)

        if parsed.needs_ocr and len(raw_text) < 50:
            document.current_revision_id = revision.id
            document.chunk_count = 0
            document.status = "needs_ocr"
            document.error = (
                "This file is a scan or an image, so it has no readable text. It is stored; "
                "reading text from images and scans (OCR) arrives in a later EZO update."
            )
            await self._clear_index(session, document)
            return

        # CHUNK
        chunks = chunk_sections(parsed.sections)
        if not chunks:
            raise ParseError("No readable text was found in the file.")
        await session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.revision_id == revision.id)
        )
        rows = [
            KnowledgeChunk(
                user_id=document.user_id,
                document_id=document.id,
                revision_id=revision.id,
                chunk_index=chunk.index,
                text=chunk.text,
                meta=chunk.metadata,
            )
            for chunk in chunks
        ]
        session.add_all(rows)
        await session.flush()

        # Old revisions stay in the database but leave the search index.
        await self._clear_index(session, document)
        document.current_revision_id = revision.id
        document.chunk_count = len(rows)

        # EMBED + INDEX
        status, error = "indexed", None
        if self.embeddings.available:
            try:
                vectors = await self.embeddings.embed_documents(
                    [f"{document.title}\n\n{row.text}" for row in rows]
                )
                store = await self.vectors.get(session)
                model = self.embeddings.model_key or ""
                await store.upsert(
                    session,
                    [
                        VectorRecord(
                            owner_type="chunk",
                            owner_id=row.id,
                            user_id=document.user_id,
                            model=model,
                            vector=vector,
                            document_id=document.id,
                            project_id=document.project_id,
                        )
                        for row, vector in zip(rows, vectors, strict=True)
                    ],
                )
                document.meta = {**document.meta, "embedding_model": model}
            except EmbeddingError as exc:
                status = "partial"
                error = (
                    f"Keyword search works, but semantic search failed: {exc.message} {exc.hint}"
                ).strip()
        else:
            status = "partial"
            error = (
                "Indexed for keyword search. Add OPENAI_API_KEY or GEMINI_API_KEY to .env and "
                "press Reindex for semantic (meaning-based) search."
            )
        document.status = status
        document.error = error
        document.indexed_at = utcnow()

    async def _revision_for(
        self, session: AsyncSession, document: KnowledgeDocument, raw_text: str
    ) -> DocumentRevision:
        latest = await session.scalar(
            select(DocumentRevision)
            .where(DocumentRevision.document_id == document.id)
            .order_by(DocumentRevision.revision_number.desc())
            .limit(1)
        )
        if latest is not None and latest.content_hash == document.content_hash:
            return latest  # re-index of unchanged content
        revision = DocumentRevision(
            document_id=document.id,
            revision_number=(latest.revision_number + 1) if latest else 1,
            content_hash=document.content_hash,
            storage_key=document.storage_key,
            raw_text=raw_text,
            meta={"size_bytes": document.size_bytes},
        )
        session.add(revision)
        await session.flush()
        return revision

    async def _clear_index(self, session: AsyncSession, document: KnowledgeDocument) -> None:
        store = await self.vectors.get(session)
        await store.delete_document(session, document.id)

    # ------------------------------------------------------------------ deleting

    async def delete_document(self, session: AsyncSession, document: KnowledgeDocument) -> None:
        keys = set(
            (
                await session.scalars(
                    select(DocumentRevision.storage_key).where(
                        DocumentRevision.document_id == document.id
                    )
                )
            ).all()
        )
        if document.storage_key:
            keys.add(document.storage_key)
        await self._clear_index(session, document)
        document.current_revision_id = None
        await session.flush()
        await session.delete(document)
        await session.flush()
        for key in keys:
            if not key:
                continue
            # Content-addressed keys may be shared by another document of the same user.
            still_used = await session.scalar(
                select(func.count()).where(KnowledgeDocument.storage_key == key)
            )
            if not still_used:
                try:
                    await self.storage.delete(key)
                except StorageError:
                    logger.warning("Could not delete stored file %s", key)


def _useful_title(title: str | None) -> str | None:
    """Ignore junk metadata titles such as 'Microsoft Word - doc1.docx'."""
    if not title:
        return None
    title = " ".join(title.split())[:300]
    lowered = title.lower()
    if (
        len(title) < 3
        or lowered.startswith(("microsoft", "untitled"))
        or lowered.endswith((".doc", ".docx", ".pdf", ".xlsx"))
    ):
        return None
    return title


__all__ = ["AddResult", "FetchError", "KnowledgeService"]
