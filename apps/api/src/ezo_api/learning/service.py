"""Knowledge OS service: register a source, read it within limits, index what was read.

Flow for one learned source (status in brackets, stored after every step so the UI and
chat show real progress, never a guess):

    add() [queued] → run(): inspect + read [inspecting → reading] → knowledge pipeline per
    document [indexing] → [indexed | partial | failed]

Reading uses only the SafeFetcher (SSRF checks, robots.txt, size and type limits). Read
text is scanned for prompt-injection attempts; matches are recorded and audit-logged,
never followed. Nothing from a source is executed.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ezo_api.db.base import utcnow
from ezo_api.db.models import KnowledgeDocument, KnowledgeLibrary, KnowledgeSource, LearnedSource
from ezo_api.knowledge.fetch import SafeFetcher
from ezo_api.knowledge.ingestion.service import KnowledgeService
from ezo_api.knowledge.retrieval.keyword import SEARCHABLE_STATUSES
from ezo_api.learning.base import Budget, Inspection, Limits
from ezo_api.learning.crawler import crawl
from ezo_api.learning.github import GitHubReader
from ezo_api.learning.packages import read_npm, read_pypi
from ezo_api.learning.safety import MAX_FLAGS, assess_license, scan_text
from ezo_api.learning.targets import Target
from ezo_api.security.audit import audit

logger = logging.getLogger(__name__)

DEFAULT_LIBRARY = "Asosiy kutubxona"
RUNNING = ("queued", "inspecting", "reading", "indexing")
SOURCE_TYPE = "learned"


class LearningError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


async def get_library(
    session: AsyncSession, user_id: uuid.UUID, name: str | None = None
) -> KnowledgeLibrary:
    """The named library (created when missing), or the default one."""
    name = " ".join((name or DEFAULT_LIBRARY).split())[:200] or DEFAULT_LIBRARY
    library = await session.scalar(
        select(KnowledgeLibrary).where(
            KnowledgeLibrary.user_id == user_id, func.lower(KnowledgeLibrary.name) == name.lower()
        )
    )
    if library is None:
        library = KnowledgeLibrary(user_id=user_id, name=name, description="")
        session.add(library)
        await session.flush()
    return library


async def resolve_library_documents(
    session: AsyncSession, *, user_id: uuid.UUID, library_id: uuid.UUID
) -> tuple[KnowledgeLibrary, frozenset[uuid.UUID]]:
    """Verify user owns library_id and resolve all authorized searchable document IDs."""
    library = await session.get(KnowledgeLibrary, library_id)
    if library is None or library.user_id != user_id:
        # 404 for another user's library too: its existence is not revealed.
        raise HTTPException(status_code=404, detail="Library not found.")
    statement = (
        select(KnowledgeDocument.id)
        .join(KnowledgeSource, KnowledgeSource.id == KnowledgeDocument.source_id)
        .join(LearnedSource, LearnedSource.knowledge_source_id == KnowledgeSource.id)
        .where(
            LearnedSource.library_id == library_id,
            LearnedSource.user_id == user_id,
            KnowledgeDocument.user_id == user_id,
            KnowledgeDocument.status.in_(SEARCHABLE_STATUSES),
            KnowledgeDocument.current_revision_id.is_not(None),
        )
    )
    doc_ids = frozenset((await session.scalars(statement)).all())
    return library, doc_ids


class LearningService:
    def __init__(
        self,
        knowledge: KnowledgeService,
        fetcher: SafeFetcher,
        sessionmaker: async_sessionmaker,  # type: ignore[type-arg]
        *,
        github_token: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.knowledge = knowledge
        self.fetcher = fetcher
        self.sessionmaker = sessionmaker
        self.github_token = github_token
        self.enabled = enabled

    # ------------------------------------------------------------------ library documents

    async def resolve_library_documents(
        self, session: AsyncSession, user_id: uuid.UUID, library_id: uuid.UUID
    ) -> tuple[KnowledgeLibrary, frozenset[uuid.UUID]]:
        """Verify user owns library_id and resolve all authorized searchable document IDs."""
        return await resolve_library_documents(session, user_id=user_id, library_id=library_id)

    # ------------------------------------------------------------------ registry

    async def add(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        target: Target,
        *,
        library: KnowledgeLibrary,
        limits: Limits | None = None,
    ) -> tuple[LearnedSource, bool]:
        """Register a source (or return the existing one in that library: (source, False))."""
        if not self.enabled:
            raise LearningError("disabled", "Learning from external sources is turned off.")
        existing = await session.scalar(
            select(LearnedSource).where(
                LearnedSource.user_id == user_id,
                LearnedSource.library_id == library.id,
                LearnedSource.target == target.key,
            )
        )
        if existing is not None:
            return existing, False
        knowledge_source = KnowledgeSource(
            user_id=user_id,
            name=target.identifier[:200],
            source_type=SOURCE_TYPE,
            source_url=target.url,
            meta={"learned": True, "library_id": str(library.id)},
        )
        session.add(knowledge_source)
        await session.flush()
        learned = LearnedSource(
            user_id=user_id,
            library_id=library.id,
            knowledge_source_id=knowledge_source.id,
            kind=target.kind,
            target=target.key,
            title=target.identifier[:300],
            status="queued",
            profile={"url": target.url},
            limits=(limits or Limits()).model_dump(),
            stats={},
            security_flags=[],
        )
        session.add(learned)
        await session.flush()
        audit(
            session,
            user_id,
            "learning.add",
            "learned_source",
            learned.id,
            {"kind": target.kind, "target": target.key, "library": library.name},
        )
        return learned, True

    async def delete(self, session: AsyncSession, learned: LearnedSource) -> int:
        """Remove the source, its documents, chunks, vectors and stored files."""
        documents = (
            await session.scalars(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.source_id == learned.knowledge_source_id
                )
            )
        ).all()
        for document in documents:
            await self.knowledge.delete_document(session, document)
        knowledge_source = await session.get(KnowledgeSource, learned.knowledge_source_id)
        audit(
            session,
            learned.user_id,
            "learning.delete",
            "learned_source",
            learned.id,
            {"target": learned.target, "documents": len(documents)},
        )
        await session.delete(learned)
        await session.flush()  # before the source, whose database cascade would remove it too
        if knowledge_source is not None:
            await session.delete(knowledge_source)
        await session.flush()
        return len(documents)

    # ------------------------------------------------------------------ reading

    async def _inspect(self, learned: LearnedSource, budget: Budget) -> Inspection:
        inspection = Inspection(title=learned.title)
        identifier = learned.target.split(":", 1)[1] if learned.kind != "website" else ""
        if learned.kind == "website":
            inspection.profile["access"] = "website"
            await crawl(self.fetcher, learned.target, budget, inspection)
            if inspection.documents:
                first = inspection.documents[0]
                inspection.title = first.title or learned.target
                inspection.profile["publisher"] = learned.target.split("/")[2]
        elif learned.kind == "github":
            reader = GitHubReader(self.fetcher, self.github_token)
            await reader.read(identifier, budget, inspection)
        elif learned.kind == "pypi":
            await read_pypi(self.fetcher, identifier, budget, inspection)
        elif learned.kind == "npm":
            await read_npm(self.fetcher, identifier, budget, inspection)
        else:
            inspection.errors.append(f"Unknown source kind {learned.kind}.")
        return inspection

    async def _set(self, session: AsyncSession, source_id: uuid.UUID, **values: Any) -> None:
        learned = await session.get(LearnedSource, source_id)
        if learned is None:
            raise LookupError(source_id)
        for key, value in values.items():
            setattr(learned, key, value)
        await session.commit()

    async def run(self, source_id: uuid.UUID) -> None:
        """Read and index one source. Never raises for source problems: the status and
        error tell what happened."""
        async with self.sessionmaker() as session:
            try:
                await self._run(session, source_id)
            except LookupError:
                logger.info("Learned source %s was deleted while it was read", source_id)
            except Exception:
                logger.exception("Learning crashed for source %s", source_id)
                await session.rollback()
                with contextlib.suppress(LookupError):
                    await self._set(
                        session,
                        source_id,
                        status="failed",
                        error="Unexpected error while reading the source. See the API logs.",
                    )

    async def _run(self, session: AsyncSession, source_id: uuid.UUID) -> None:
        learned = await session.get(LearnedSource, source_id)
        if learned is None:
            raise LookupError(source_id)
        user_id = learned.user_id
        knowledge_source_id = learned.knowledge_source_id
        limits = Limits.model_validate(learned.limits or {})
        await self._set(session, source_id, status="inspecting", error=None)
        learned = await session.get(LearnedSource, source_id)
        assert learned is not None

        budget = Budget(limits)
        inspection = await self._inspect(learned, budget)
        await self._set(session, source_id, status="reading" if inspection.documents else "failed")

        flags: list[dict[str, str]] = []
        for document in inspection.documents:
            if len(flags) < MAX_FLAGS:
                text = document.data[:400_000].decode("utf-8", errors="replace")
                flags.extend(f.as_dict() for f in scan_text(text, document.url))
        flags = flags[:MAX_FLAGS]

        await self._set(session, source_id, status="indexing")
        knowledge_source = await session.get(KnowledgeSource, knowledge_source_id)
        if knowledge_source is None:
            raise LookupError(source_id)
        seen_urls: set[str] = set()
        hashes: list[str] = []
        manifest: list[dict[str, str | None]] = []
        changed = 0
        for document in inspection.documents:
            if document.url in seen_urls:
                continue
            seen_urls.add(document.url)
            result = await self.knowledge.add_source_document(
                session,
                knowledge_source,
                url=document.url,
                filename=document.filename,
                title=document.title,
                data=document.data,
                category=document.category,
                meta={**document.meta, "learned_source_id": str(source_id)},
            )
            hashes.append(result.document.content_hash or "")
            document_id = result.document.id
            await session.commit()
            if not result.duplicate:
                changed += 1
            # Content deduplication does not prove index publication succeeded.
            # A crash can follow file registration or the processing-status
            # commit. Resume only those incomplete states; do not revive failed
            # documents or reindex healthy unchanged revisions automatically.
            if not result.duplicate or result.document.status in ("queued", "processing"):
                await self.knowledge.ingest(session, document_id)
            indexed_document = await session.get(KnowledgeDocument, document_id)
            if indexed_document is None:
                raise LookupError(source_id)
            manifest.append(
                {
                    "document_id": str(document_id),
                    "revision_id": (
                        str(indexed_document.current_revision_id)
                        if indexed_document.current_revision_id
                        else None
                    ),
                    "content_hash": indexed_document.content_hash,
                }
            )
            knowledge_source = await session.get(KnowledgeSource, knowledge_source_id)
            if knowledge_source is None:
                raise LookupError(source_id)

        # A complete run replaces the previous one: documents no longer in the source go.
        removed = 0
        if inspection.documents and inspection.stopped is None and not inspection.errors:
            old = (
                await session.scalars(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.source_id == knowledge_source_id,
                        KnowledgeDocument.source_url.not_in(seen_urls),
                    )
                )
            ).all()
            for document_row in old:
                await self.knowledge.delete_document(session, document_row)
                removed += 1

        statuses = dict(
            (
                await session.execute(
                    select(KnowledgeDocument.status, func.count())
                    .where(KnowledgeDocument.source_id == knowledge_source_id)
                    .group_by(KnowledgeDocument.status)
                )
            ).all()
        )
        indexed = int(statuses.get("indexed", 0))
        keyword_only = int(statuses.get("partial", 0))
        failed_docs = sum(int(v) for k, v in statuses.items() if k not in ("indexed", "partial"))
        usable = indexed + keyword_only
        if usable == 0:
            status = "failed"
        elif (
            inspection.errors
            or inspection.stopped
            or failed_docs
            or inspection.profile.get("access") == "raw_fallback"
        ):
            status = "partial"
        else:
            status = "indexed"
        error = "; ".join(inspection.errors)[:2000] or (
            None if usable else "Nothing readable was found in this source."
        )
        license_review = assess_license(inspection.license)
        content_hash = hashlib.sha256("".join(sorted(hashes)).encode()).hexdigest()
        learned = await session.get(LearnedSource, source_id)
        if learned is None:
            raise LookupError(source_id)
        previous_hash = learned.content_hash
        learned.title = (inspection.title or learned.title)[:300]
        learned.version = str(inspection.version)[:200] if inspection.version else None
        found_license = license_review["license"]
        learned.license = str(found_license)[:200] if found_license else None
        learned.profile = {
            **(learned.profile or {}),
            **inspection.profile,
            "license_review": license_review,
            "skipped": inspection.skipped[:100],
        }
        learned.stats = {
            "documents": len(seen_urls),
            "indexed": indexed,
            "keyword_only": keyword_only,
            "failed": failed_docs,
            "changed": changed,
            "removed": removed,
            "skipped": len(inspection.skipped),
            "requests": budget.requests,
            "bytes": budget.bytes,
            "stopped": inspection.stopped,
            "seconds": round(time.monotonic() - budget.started, 1),
            "content_changed": previous_hash is not None and previous_hash != content_hash,
        }
        learned.security_flags = flags
        learned.status = status
        learned.error = error
        learned.content_hash = content_hash if seen_urls else learned.content_hash
        learned.last_checked_at = utcnow()
        if usable:
            learned.indexed_at = utcnow()
        knowledge_source.last_sync_at = utcnow()
        knowledge_source.name = learned.title[:200]
        if flags:
            audit(
                session,
                user_id,
                "learning.injection_suspected",
                "learned_source",
                source_id,
                {"count": len(flags), "kinds": sorted({f["kind"] for f in flags})},
            )
        audit(
            session,
            user_id,
            "learning.read",
            "learned_source",
            source_id,
            {"status": status, "documents": len(seen_urls), "stopped": inspection.stopped},
        )
        # Immutable-by-API, bounded provenance for this actual completed attempt.
        # No raw source, credentials or full extracted text enters the audit payload.
        # A partial fetch is explicitly partial; this is not a whole-source snapshot.
        audit(
            session,
            user_id,
            "learning.source_version",
            "learned_source",
            source_id,
            {
                "schema": "source-version-v1",
                "content_hash": learned.content_hash,
                "previous_content_hash": previous_hash,
                "version": learned.version,
                "status": status,
                "complete_fetch": bool(inspection.documents)
                and inspection.stopped is None
                and not inspection.errors,
                "documents": manifest[:200],
                "manifest_truncated": len(manifest) > 200,
                "changed": changed,
                "removed": removed,
            },
        )
        await session.commit()


class LearningRunner:
    """Runs learning jobs in the background (or inline for tests and small setups).
    Jobs interrupted by a restart are started again at startup."""

    def __init__(self, service: LearningService, mode: str = "background") -> None:
        self.service = service
        self.mode = mode
        self._semaphore = asyncio.Semaphore(1)
        self._tasks: set[asyncio.Task[None]] = set()

    async def _run(self, source_id: uuid.UUID) -> None:
        async with self._semaphore:
            await self.service.run(source_id)

    async def submit(self, source_id: uuid.UUID) -> None:
        if self.mode == "inline":
            await self._run(source_id)
            return
        task = asyncio.create_task(self._run(source_id), name=f"learn-{source_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def resume_unfinished(self) -> int:
        async with self.service.sessionmaker() as session:
            ids = (
                await session.scalars(
                    select(LearnedSource.id).where(LearnedSource.status.in_(RUNNING))
                )
            ).all()
        for source_id in ids:
            await self.submit(source_id)
        return len(ids)

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
