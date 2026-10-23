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
from dataclasses import dataclass, field

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.language import detect_language
from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DocumentRevision,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    OcrPage,
)
from ezo_api.documents.isolation import ISOLATION_MESSAGE, native_fixtures_allowed
from ezo_api.documents.ocr import NoOCRProvider, OCRError, OCRProvider
from ezo_api.documents.pdf.engine import PdfError, inspect_pdf
from ezo_api.knowledge.embeddings.service import EmbeddingError, EmbeddingService
from ezo_api.knowledge.fetch import FetchError, SafeFetcher
from ezo_api.knowledge.ingestion.chunking import chunk_sections
from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.parsers import ParseError, parse
from ezo_api.knowledge.parsers.base import ParsedDocument, Section
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


class IngestionSuperseded(LookupError):
    """The input changed while an older ingestion was between commit boundaries."""


@dataclass(slots=True)
class OcrOutcome:
    engine_available: bool
    ran: bool = False
    whole_file: bool = False
    pages: set[int] = field(default_factory=set)
    reason: str = ""
    error: str | None = None
    incomplete: str | None = None

    def covers(self, page_start: int | None, page_end: int | None) -> bool:
        if self.whole_file:
            return True
        if page_start is None or not self.pages:
            return False
        return any(p in self.pages for p in range(page_start, (page_end or page_start) + 1))

    def failure_message(self) -> str:
        """Why a scan or image ended up without readable text (shown to the user)."""
        if self.error:
            return f"This file is a scan or an image. OCR could not read it: {self.error}"
        if self.ran:
            return (
                "This file is a scan or an image. OCR (Tesseract) ran but found no readable "
                "text; the image may be too blurry, too small or contain no text."
            )
        return (
            "This file is a scan or an image, so it has no text layer. It is stored, but OCR "
            "is not available on this server" + (f": {self.reason}" if self.reason else ".")
        )


class KnowledgeService:
    def __init__(
        self,
        storage: StorageProvider,
        embeddings: EmbeddingService,
        vectors: VectorStoreResolver,
        fetcher: SafeFetcher,
        max_upload_bytes: int,
        ocr: OCRProvider | None = None,
    ) -> None:
        self.ocr = ocr or NoOCRProvider()
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
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        content_hash: str,
        project_id: uuid.UUID | None,
    ) -> KnowledgeDocument | None:
        return await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user_id,
                KnowledgeDocument.content_hash == content_hash,
                KnowledgeDocument.project_id.is_not_distinct_from(project_id),
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
        if not native_fixtures_allowed() and extension_of(safe_name) not in (
            ".txt",
            ".md",
            ".markdown",
            ".csv",
        ):
            raise UploadRejectedError("isolation_unavailable", ISOLATION_MESSAGE)
        if not native_fixtures_allowed() and len(data) > 2_000_000:
            raise UploadRejectedError("too_large", "Safe text ingestion is limited to 2 MB.")
        kind = detect_kind(safe_name, data)
        content_hash = sha256_hex(data)

        existing = await self._duplicate_of(session, user_id, content_hash, project_id)
        if existing is not None:
            return AddResult(existing, duplicate=True, new_revision=False)

        key = (
            f"uploads/{user_id}/{project_id or 'inbox'}/"
            f"{content_hash[:2]}/{content_hash}{extension_of(safe_name)}"
        )
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
        existing = await self._duplicate_of(session, user_id, content_hash, project_id)
        if existing is not None:
            return AddResult(existing, duplicate=True, new_revision=False)

        ext = {"pdf": ".pdf", "html": ".html"}.get(category, ".txt")
        key = f"web/{user_id}/{project_id or 'inbox'}/{content_hash[:2]}/{content_hash}{ext}"
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

    async def add_connector_document(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        source_name: str,
        source_url: str,
        filename: str,
        title: str,
        markdown: str,
        meta: dict[str, object],
    ) -> AddResult:
        """Add (or revise) one document delivered by a connector, e.g. an official source.

        The text is stored as Markdown so its sections (articles) survive chunking. One
        knowledge source per connector; the document is keyed by its official URL.
        """
        data = markdown.encode("utf-8")
        content_hash = sha256_hex(data)
        source = await session.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.user_id == user_id,
                KnowledgeSource.source_type == "connector",
                KnowledgeSource.name == source_name,
                KnowledgeSource.project_id.is_(None),
            )
        )
        if source is None:
            source = KnowledgeSource(
                user_id=user_id, name=source_name, source_type="connector", meta={}
            )
            session.add(source)
            await session.flush()
        source.last_sync_at = utcnow()
        document = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_id == source.id,
                KnowledgeDocument.source_url == source_url,
            )
        )
        if document is not None and document.content_hash == content_hash:
            return AddResult(document, duplicate=True, new_revision=False)
        key = f"connectors/{user_id}/{content_hash[:2]}/{content_hash}.md"
        await self.storage.put(key, data)
        new_revision = document is not None
        if document is None:
            document = KnowledgeDocument(
                user_id=user_id,
                source_id=source.id,
                title=title[:300],
                filename=sanitize_filename(filename),
                source_url=source_url,
                mime_type="text/markdown",
                meta={},
            )
            session.add(document)
        document.title = title[:300]
        document.storage_key = key
        document.size_bytes = len(data)
        document.content_hash = content_hash
        document.status = "queued"
        document.error = None
        document.meta = {**(document.meta or {}), **meta, "category": "markdown"}
        await session.flush()
        return AddResult(document, duplicate=False, new_revision=new_revision)

    async def add_source_document(
        self,
        session: AsyncSession,
        source: KnowledgeSource,
        *,
        url: str,
        filename: str,
        title: str,
        data: bytes,
        category: str,
        meta: dict[str, object],
    ) -> AddResult:
        """Add (or revise) one document of a learned source, keyed by its URL inside that
        source. Unchanged content is reported as a duplicate and not re-indexed."""
        content_hash = sha256_hex(data)
        document = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_id == source.id, KnowledgeDocument.source_url == url
            )
        )
        if document is not None and document.content_hash == content_hash:
            return AddResult(document, duplicate=True, new_revision=False)
        ext = {"pdf": ".pdf", "html": ".html", "markdown": ".md"}.get(category, ".txt")
        key = f"learned/{source.user_id}/{content_hash[:2]}/{content_hash}{ext}"
        await self.storage.put(key, data)
        mime = {
            "pdf": "application/pdf",
            "html": "text/html",
            "markdown": "text/markdown",
        }.get(category, "text/plain")
        new_revision = document is not None
        if document is None:
            document = KnowledgeDocument(
                user_id=source.user_id,
                source_id=source.id,
                project_id=source.project_id,
                source_url=url,
                meta={},
            )
            session.add(document)
        document.title = title[:300] or url[:300]
        document.filename = sanitize_filename(filename)
        document.mime_type = mime
        document.storage_key = key
        document.size_bytes = len(data)
        document.content_hash = content_hash
        document.status = "queued"
        document.error = None
        document.meta = {**(document.meta or {}), **meta, "category": category}
        await session.flush()
        return AddResult(document, duplicate=False, new_revision=new_revision)

    # ------------------------------------------------------------------ ingest

    async def ingest(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        *,
        expected_hash: str | None = None,
    ) -> KnowledgeDocument:
        """Process queued/processing input; explicit reindex must queue it first.

        Duplicate runners reuse a terminal result. Never raises for content problems:
        the document ends up `indexed`, `partial`, `needs_ocr` or `failed` with a message."""
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:
            raise LookupError(f"Document {document_id} not found")
        if (document.meta or {}).get("student") is True:
            # Student raw revisions have no legacy storage pointer. Their current
            # revision/index/status belong exclusively to fenced publication.
            return document
        document = await self._locked_input(session, document_id, expected_hash)
        if not self._pending(document):
            await session.commit()
            return document
        input_hash = document.content_hash
        document.status = "processing"
        document.error = None
        await session.commit()
        # Keep processing progress visible, then reacquire and refresh under a
        # write lock. Another runner may have completed or replaced this input
        # between those transactions. Never rebuild its committed chunk set.
        document = await self._locked_input(session, document_id, input_hash)
        if not self._pending(document):
            await session.commit()
            return document
        try:
            await self._run_pipeline(session, document)
        except (ParseError, StorageError, UploadRejectedError) as exc:
            await session.rollback()
            document = await self._locked_input(session, document_id, input_hash)
            if not self._pending(document):
                await session.commit()
                return document
            document.status = "failed"
            document.error = getattr(exc, "message", None) or str(exc)
        except Exception:
            logger.error("Ingestion crashed for document %s", document_id)
            await session.rollback()
            document = await self._locked_input(session, document_id, input_hash)
            if not self._pending(document):
                await session.commit()
                return document
            document.status = "failed"
            document.error = "Unexpected error while reading the file. See the API logs."
        await session.commit()
        return document

    @staticmethod
    def _pending(document: KnowledgeDocument) -> bool:
        return (document.meta or {}).get("student") is not True and document.status in (
            "queued",
            "processing",
        )

    async def _locked_input(
        self, session: AsyncSession, document_id: uuid.UUID, expected_hash: str | None
    ) -> KnowledgeDocument:
        # SELECT FOR UPDATE is ignored by SQLite. A no-op UPDATE locks the row
        # on PostgreSQL and the writer on SQLite; refresh the identity map too.
        document = await session.scalar(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(updated_at=KnowledgeDocument.updated_at)
            .returning(KnowledgeDocument)
            .execution_options(populate_existing=True)
        )
        if document is None:
            await session.rollback()
            raise LookupError(f"Document {document_id} not found")
        if expected_hash is not None and document.content_hash != expected_hash:
            await session.rollback()
            raise IngestionSuperseded("Document input was superseded")
        return document

    async def _run_pipeline(self, session: AsyncSession, document: KnowledgeDocument) -> None:
        # FETCH
        if not document.storage_key:
            raise StorageError("The document has no stored file.")
        data = await self.storage.get(document.storage_key)
        if document.content_hash and sha256_hex(data) != document.content_hash:
            raise ParseError("Stored document integrity check failed.", "integrity_mismatch")

        # PARSE (CPU-bound: off the event loop)
        category = str((document.meta or {}).get("category", "text"))
        if not native_fixtures_allowed() and category not in ("text", "markdown", "csv", "html"):
            raise ParseError(ISOLATION_MESSAGE, "isolation_unavailable")
        parsed = await asyncio.to_thread(parse, category, data, document.filename or "file")

        # OCR: pages without a text layer (scans, photos), when an engine is installed.
        ocr = await self._ocr(session, document, data, category, parsed)

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
            document.error = ocr.failure_message()
            await self._clear_index(session, document)
            return

        # CHUNK
        chunks = chunk_sections(parsed.sections)
        if not chunks:
            raise ParseError("No readable text was found in the file.")
        for chunk in chunks:
            if ocr.covers(chunk.metadata.get("page_start"), chunk.metadata.get("page_end")):
                chunk.metadata["ocr"] = True
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
        if ocr.incomplete:
            status = "partial"
            error = " ".join(part for part in (ocr.incomplete, error) if part)
        document.status = status
        document.error = error
        document.indexed_at = utcnow()

    async def _ocr(
        self,
        session: AsyncSession,
        document: KnowledgeDocument,
        data: bytes,
        category: str,
        parsed: ParsedDocument,
    ) -> OcrOutcome:
        """Read pages that have no text layer with the OCR engine. Section texts of those
        pages are replaced by what OCR read; nothing is invented for unreadable pages.
        The per-page results (text, lines with coordinates, languages, engine confidence,
        preprocessing) are stored in `ocr_pages`."""
        outcome = OcrOutcome(engine_available=self.ocr.available)
        document.meta = {k: v for k, v in (document.meta or {}).items() if k != "ocr"}
        if category == "image":
            targets: list[int] | None = None
        elif category == "pdf":
            # Pages with no text layer, or a few characters on top of an image (a scan with
            # a stamped page number). Short text-only pages are not scans.
            try:
                targets = (await asyncio.to_thread(inspect_pdf, data)).scanned_pages
            except PdfError:
                targets = [
                    s.page for s in parsed.sections if s.page is not None and not s.text.strip()
                ]
            if not targets:
                return outcome
        else:
            return outcome
        await session.execute(delete(OcrPage).where(OcrPage.document_id == document.id))
        if not self.ocr.available:
            outcome.reason = str(self.ocr.status().get("reason") or "")
            return outcome
        try:
            result = await self.ocr.extract(data, document.mime_type, pages=targets)
        except OCRError as exc:
            outcome.error = exc.message
            document.meta = {**document.meta, "ocr": {"error": exc.message}}
            return outcome
        outcome.ran = True
        read = {page.number: page for page in result.pages if page.text.strip()}
        if category == "image":
            if 1 in read:
                parsed.sections = [Section(text=read[1].text)]
                outcome.whole_file = True
        else:
            for section in parsed.sections:
                if section.page in read:
                    section.text = read[section.page].text
            outcome.pages = set(read)
        session.add_all(
            OcrPage(
                user_id=document.user_id,
                document_id=document.id,
                page_number=page.number,
                text=page.text,
                lines=page.lines_json(),
                width=page.width,
                height=page.height,
                dpi=page.dpi,
                languages=page.languages,
                script=page.script,
                detected_language=page.detected_language,
                method=result.engine,
                engine_version=result.engine_version[:60],
                confidence=page.confidence,
                rotation=page.rotation,
                deskew_angle=page.deskew_angle,
                source_content_hash=document.content_hash,
                page_image_sha256=page.source_sha256,
                warnings=page.warnings,
            )
            for page in result.pages
        )
        document.meta = {**document.meta, "ocr": result.summary()}
        outcome.incomplete = next((w for w in result.warnings if "were not read" in w), None)
        return outcome

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
                select(
                    or_(
                        exists().where(KnowledgeDocument.storage_key == key),
                        exists().where(DocumentRevision.storage_key == key),
                    )
                )
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
