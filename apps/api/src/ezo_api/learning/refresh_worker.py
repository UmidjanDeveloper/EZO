"""Staged refresh with one atomic, fenced SQL publication and fixed work budgets."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import exists, or_, select

from ezo_api.core.language import detect_language
from ezo_api.db.models import (
    DocumentRevision,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    LearnedSource,
    SourceRefreshBlob,
)
from ezo_api.documents.isolation import ISOLATION_MESSAGE, native_fixtures_allowed
from ezo_api.knowledge.embeddings.service import EmbeddingError
from ezo_api.knowledge.ingestion.chunking import Chunk, chunk_sections
from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.jobs.service import JobError
from ezo_api.knowledge.parsers import ParseError, parse
from ezo_api.knowledge.uploads import sanitize_filename, sha256_hex
from ezo_api.knowledge.vectorstores import VectorRecord
from ezo_api.learning.base import Budget, Inspection, Limits, ReadDocument
from ezo_api.learning.refresh import RefreshLease, RefreshQueue, fingerprint
from ezo_api.learning.safety import MAX_FLAGS, assess_license, scan_text
from ezo_api.learning.service import LearningService
from ezo_api.security.audit import audit
from ezo_api.storage.base import StorageError

logger = logging.getLogger(__name__)

MAX_DOCUMENTS = 200
MAX_INPUT_BYTES = 20_000_000
MAX_TEXT_CHARS = 5_000_000
MAX_CHUNKS = 2000
MAX_VECTOR_DIM = 4096


@dataclass
class Prepared:
    read: ReadDocument
    content_hash: str
    storage_key: str
    text: str
    chunks: list[Chunk]
    vectors: list[list[float]] | None
    model: str | None
    error: str | None


class RefreshWorker:
    def __init__(self, queue: RefreshQueue, learning: LearningService) -> None:
        self.queue, self.learning = queue, learning

    async def inspect(self, lease: RefreshLease, budget: Budget) -> Inspection:
        if not self.learning.enabled:
            raise JobError("learning_disabled", "Source learning is disabled.")
        requests = 0
        network_bytes = 0

        async def admit() -> None:
            nonlocal requests
            await self.queue.check(lease)
            requests += 1
            if requests > 500:
                raise JobError("resource_limit", "Refresh network request limit exceeded.")

        def consume(size: int) -> None:
            nonlocal network_bytes
            network_bytes += size
            if network_bytes > min(MAX_INPUT_BYTES, int(budget.limits.max_total_mb * 1024 * 1024)):
                raise JobError("resource_limit", "Refresh network byte limit exceeded.")

        # A dedicated reader uses the same safe transport policy but never mutates
        # a global fetcher, shared credentials or another job's admission callback.
        reader = LearningService(
            self.learning.knowledge,
            self.learning.fetcher.scoped(admit, consume),
            self.learning.sessionmaker,
            github_token=self.learning.github_token,
            enabled=self.learning.enabled,
        )
        source = LearnedSource(
            kind=lease.input["kind"], target=lease.input["target"], title=lease.input["title"]
        )
        return await reader._inspect(source, budget)

    async def prepare(self, lease: RefreshLease, inspection: Inspection) -> list[Prepared]:
        if len(inspection.documents) > MAX_DOCUMENTS:
            raise JobError("resource_limit", "Refresh document limit exceeded.")
        total_bytes = sum(len(d.data) for d in inspection.documents)
        if total_bytes > MAX_INPUT_BYTES:
            raise JobError("resource_limit", "Refresh document byte limit exceeded.")
        async with self.queue.transaction(write=False) as session:
            old = list(
                (
                    await session.scalars(
                        select(KnowledgeDocument).where(
                            KnowledgeDocument.source_id
                            == uuid.UUID(lease.input["knowledge_source_id"]),
                            KnowledgeDocument.status != "removed",
                        )
                    )
                ).all()
            )
            # Any replacement during discovery invalidates the whole attempt.
            if fingerprint(old) != lease.input["documents"]:
                raise JobError(
                    "input_changed", "Source documents changed since refresh was requested."
                )
            unchanged = {
                d.source_url: d.content_hash
                for d in old
                if d.status not in ("queued", "processing", "removed")
            }
        knowledge = self.learning.knowledge
        prepared: list[Prepared] = []
        seen: set[str] = set()
        chars, chunk_count = 0, 0
        for document in inspection.documents:
            await self.queue.check(lease)
            if document.url in seen:
                continue
            seen.add(document.url)
            digest = sha256_hex(document.data)
            if unchanged.get(document.url) == digest:
                continue
            # Retain the main API native isolation guard. This is not a native worker.
            if not native_fixtures_allowed() and document.category not in (
                "text",
                "markdown",
                "csv",
                "html",
            ):
                raise JobError("isolation_unavailable", ISOLATION_MESSAGE)
            if len(document.data) > 2_000_000:
                raise JobError("resource_limit", "One refresh document is limited to 2 MB.")
            parsed = await asyncio.to_thread(
                parse, document.category, document.data, document.filename
            )
            document.meta = {**document.meta, **parsed.metadata}
            value = normalize_text(parsed.text)
            if parsed.needs_ocr or not value:
                raise JobError(
                    "unreadable_document", "A source document requires an isolated parser or OCR."
                )
            chunks = chunk_sections(parsed.sections)
            chars += len(value)
            chunk_count += len(chunks)
            if chars > MAX_TEXT_CHARS or chunk_count > MAX_CHUNKS:
                raise JobError("resource_limit", "Refresh extracted-text or chunk limit exceeded.")
            vectors, model, error = None, None, None
            if knowledge.embeddings.available:
                try:
                    vectors = await knowledge.embeddings.embed_documents(
                        [f"{document.title}\n\n{c.text}" for c in chunks],
                        before_batch=lambda: self.queue.check(lease),
                    )
                    if len(vectors) != len(chunks) or any(
                        not v or len(v) > MAX_VECTOR_DIM or any(not math.isfinite(x) for x in v)
                        for v in vectors
                    ):
                        raise EmbeddingError("Embedding output exceeds refresh policy.")
                    model = knowledge.embeddings.model_key
                except EmbeddingError:
                    vectors = None
                    error = (
                        "Keyword search works; semantic indexing was unavailable for this refresh."
                    )
            else:
                error = "Indexed for keyword search; no embedding provider is configured."
            # Attempt-specific immutable object keys; stale work cannot overwrite a
            # currently published revision's bytes, even after losing its lease.
            suffix = {"markdown": ".md", "html": ".html", "pdf": ".pdf"}.get(
                document.category, ".txt"
            )
            path_hash = hashlib.sha256(document.url.encode()).hexdigest()[:24]
            key = (
                f"refresh/{lease.user_id}/{lease.run_id}/{lease.attempt}/"
                f"{path_hash}-{digest}{suffix}"
            )
            await self.queue.journal(lease, key)  # committed BEFORE any object write
            await knowledge.storage.put(key, document.data)
            if sha256_hex(await knowledge.storage.get(key)) != digest:
                raise JobError("integrity_mismatch", "Staged source storage checksum mismatch.")
            prepared.append(Prepared(document, digest, key, value, chunks, vectors, model, error))
        return prepared

    async def publish(
        self, lease: RefreshLease, inspection: Inspection, prepared: list[Prepared], budget: Budget
    ) -> None:
        knowledge = self.learning.knowledge
        async with self.queue.transaction() as session:
            source, run = await self.queue.fence(session, lease)
            if (
                source.kind != lease.input["kind"]
                or source.target != lease.input["target"]
                or str(source.knowledge_source_id) != lease.input["knowledge_source_id"]
            ):
                raise JobError("input_changed", "Source registration changed during refresh.")
            knowledge_source = await session.get(KnowledgeSource, source.knowledge_source_id)
            if knowledge_source is None or (
                str(knowledge_source.project_id) if knowledge_source.project_id else None
            ) != lease.input.get("project_id"):
                raise JobError("input_changed", "Source project changed during refresh.")
            docs = list(
                (
                    await session.scalars(
                        select(KnowledgeDocument)
                        .where(
                            KnowledgeDocument.source_id == source.knowledge_source_id,
                            or_(
                                KnowledgeDocument.status != "removed",
                                KnowledgeDocument.source_url.in_(
                                    [d.url for d in inspection.documents]
                                ),
                            ),
                        )
                        .order_by(KnowledgeDocument.id)
                        .with_for_update()
                    )
                ).all()
            )
            if fingerprint([d for d in docs if d.status != "removed"]) != lease.input[
                "documents"
            ] or any(d.user_id != lease.user_id for d in docs):
                raise JobError("input_changed", "Source documents changed during refresh.")
            indexed = {d.source_url: d for d in docs}
            changed = 0
            for stage in prepared:
                document = indexed.get(stage.read.url)
                if document is None:
                    document = KnowledgeDocument(
                        user_id=lease.user_id,
                        source_id=source.knowledge_source_id,
                        project_id=knowledge_source.project_id,
                        title=stage.read.title[:300],
                        content_hash=stage.content_hash,
                        storage_key=stage.storage_key,
                        mime_type="text/plain",
                        source_url=stage.read.url,
                        meta={},
                    )
                    session.add(document)
                    await session.flush()
                    indexed[stage.read.url] = document
                number = await session.scalar(
                    select(DocumentRevision.revision_number)
                    .where(DocumentRevision.document_id == document.id)
                    .order_by(DocumentRevision.revision_number.desc())
                    .limit(1)
                )
                revision = DocumentRevision(
                    document_id=document.id,
                    revision_number=(number or 0) + 1,
                    content_hash=stage.content_hash,
                    storage_key=stage.storage_key,
                    raw_text=stage.text,
                    meta={"size_bytes": len(stage.read.data), "refresh_run_id": str(lease.run_id)},
                )
                session.add(revision)
                await session.flush()
                rows = [
                    KnowledgeChunk(
                        user_id=lease.user_id,
                        document_id=document.id,
                        revision_id=revision.id,
                        chunk_index=c.index,
                        text=c.text,
                        meta=c.metadata,
                    )
                    for c in stage.chunks
                ]
                session.add_all(rows)
                await session.flush()
                store = await knowledge.vectors.get(session)
                await store.delete_document(session, document.id)
                if stage.vectors is not None and stage.model:
                    await store.upsert(
                        session,
                        [
                            VectorRecord(
                                "chunk",
                                row.id,
                                lease.user_id,
                                stage.model,
                                vector,
                                document_id=document.id,
                                project_id=document.project_id,
                            )
                            for row, vector in zip(rows, stage.vectors, strict=True)
                        ],
                    )
                document.current_revision_id = revision.id
                document.content_hash, document.storage_key = stage.content_hash, stage.storage_key
                document.title, document.filename = (
                    stage.read.title[:300],
                    sanitize_filename(stage.read.filename),
                )
                document.mime_type = {
                    "markdown": "text/markdown",
                    "html": "text/html",
                    "pdf": "application/pdf",
                }.get(stage.read.category, "text/plain")
                document.language = detect_language(stage.text[:5000])
                document.size_bytes, document.chunk_count = len(stage.read.data), len(rows)
                document.meta = {
                    **(document.meta or {}),
                    **stage.read.meta,
                    "category": stage.read.category,
                    "chars": len(stage.text),
                    "refresh_run_id": str(lease.run_id),
                    "embedding_model": stage.model,
                }
                document.status, document.error = (
                    ("indexed" if stage.vectors is not None else "partial"),
                    stage.error,
                )
                document.indexed_at = await self.queue.now(session)
                blob = await session.scalar(
                    select(SourceRefreshBlob).where(
                        SourceRefreshBlob.storage_key == stage.storage_key
                    )
                )
                if blob is None or blob.run_id != lease.run_id:
                    raise JobError("integrity_mismatch", "Refresh storage provenance is missing.")
                blob.published = True
                changed += 1
            seen_urls = {d.url for d in inspection.documents}
            complete = bool(seen_urls) and not inspection.errors and inspection.stopped is None
            removed = 0
            if complete:
                # Preserve immutable revisions/provenance. Withdraw the current
                # search pointer, rather than deleting a historical source version.
                for url, document in indexed.items():
                    if url not in seen_urls and document.status != "removed":
                        store = await knowledge.vectors.get(session)
                        await store.delete_document(session, document.id)
                        document.status, document.current_revision_id, document.chunk_count = (
                            "removed",
                            None,
                            0,
                        )
                        removed += 1
            observation_time = (await self.queue.now(session)).isoformat()
            changed_urls = {stage.read.url for stage in prepared}
            for url, document in indexed.items():
                prior_observation = (document.meta or {}).get("refresh_observation", {})
                prior_observation = prior_observation if isinstance(prior_observation, dict) else {}
                seen = url in seen_urls
                document.meta = {
                    **(document.meta or {}),
                    "refresh_observation": {
                        "run_id": str(lease.run_id),
                        "seen": seen,
                        "complete_fetch": complete,
                        "checked_at": observation_time if seen else None,
                        "last_seen_at": observation_time
                        if seen
                        else prior_observation.get("last_seen_at"),
                        "content_changed": url in changed_urls,
                    },
                }
            manifest = []
            for url in sorted(seen_urls):
                document = indexed.get(url)
                if document is None:
                    raise JobError("integrity_mismatch", "Refresh manifest has no document.")
                manifest.append(
                    {
                        "document_id": str(document.id),
                        "revision_id": str(document.current_revision_id)
                        if document.current_revision_id
                        else None,
                        "content_hash": document.content_hash,
                        "status": document.status,
                    }
                )
            usable = [m for m in manifest if m["status"] in ("indexed", "partial")]
            if not usable:
                raise JobError(
                    "nothing_readable",
                    "No readable source content was found; previous publication is preserved.",
                )
            status = (
                "indexed"
                if complete and all(m["status"] == "indexed" for m in manifest)
                else "partial"
            )
            previous = source.content_hash
            digest = sha256_hex("".join(sorted(str(m["content_hash"]) for m in manifest)).encode())
            flags = [
                f.as_dict()
                for d in inspection.documents
                for f in scan_text(d.data[:400_000].decode("utf-8", errors="replace"), d.url)
            ][:MAX_FLAGS]
            source.title = (inspection.title or source.title)[:300]
            source.version = str(inspection.version)[:200] if inspection.version else None
            review = assess_license(inspection.license)
            source.license = str(review["license"])[:200] if review["license"] else None
            source.profile = {
                **{k: v for k, v in (source.profile or {}).items() if k != "capability_analysis"},
                **inspection.profile,
                "license_review": review,
                "skipped": inspection.skipped[:100],
            }
            source.content_hash, source.security_flags = digest, flags
            source.status, source.error = status, "; ".join(inspection.errors)[:2000] or None
            source.stats = {
                "documents": len(manifest),
                "changed": changed,
                "removed": removed,
                "requests": budget.requests,
                "bytes": budget.bytes,
                "stopped": inspection.stopped,
                "content_changed": previous is not None and previous != digest,
            }
            source.last_checked_at = source.indexed_at = await self.queue.now(session)
            ks = await session.get(KnowledgeSource, source.knowledge_source_id)
            assert ks is not None
            ks.name, ks.last_sync_at = source.title[:200], source.last_checked_at
            result = {
                "schema": "source-version-v2",
                "run_id": str(lease.run_id),
                "attempt": lease.attempt,
                "source_status": status,
                "content_hash": digest,
                "previous_content_hash": previous,
                "complete_fetch": complete,
                "documents": manifest,
                "changed": changed,
                "removed": removed,
                "generation": lease.generation,
            }
            run.result = result
            # Check the actual database clock again after vector SQL, never just
            # at transaction entry. A delayed publication must roll back in full.
            now = await self.queue.now(session)
            if run.lease_until is None or run.lease_until <= now:
                raise JobError("stale_lease", "Refresh deadline expired before publication.")
            self.queue.terminal(run, "completed", now)
            audit(
                session,
                lease.user_id,
                "learning.source_version",
                "learned_source",
                source.id,
                {
                    **result,
                    "documents": [{k: v for k, v in m.items() if k != "status"} for m in manifest],
                },
            )
            if flags:
                audit(
                    session,
                    lease.user_id,
                    "learning.injection_suspected",
                    "learned_source",
                    source.id,
                    {"count": len(flags), "kinds": sorted({f["kind"] for f in flags})},
                )

    async def process_one(self) -> bool:
        if not self.learning.enabled:
            return False
        lease = await self.queue.claim()
        if lease is None:
            return False
        try:
            async with asyncio.timeout(Limits.model_validate(lease.input["limits"]).max_seconds):
                budget = Budget(Limits.model_validate(lease.input["limits"]))
                inspection = await self.inspect(lease, budget)
                stage = await self.prepare(lease, inspection)
                await self.publish(lease, inspection, stage, budget)
        except asyncio.CancelledError:
            # Leave the durable lease to expire; never refund or reset attempts.
            raise
        except (JobError, ParseError, StorageError, TimeoutError) as exc:
            code = (
                exc.code
                if isinstance(exc, JobError | ParseError)
                else "storage_unavailable"
                if isinstance(exc, StorageError)
                else "deadline"
            )
            with contextlib.suppress(JobError):
                await self.queue.fail(
                    lease, code, transient=isinstance(exc, StorageError | TimeoutError)
                )
            logger.info("Refresh attempt ended (%s)", code)
        except Exception:
            logger.exception("Refresh failed (%s)", lease.run_id)
            with contextlib.suppress(JobError):
                await self.queue.fail(lease, "internal_error")
        return True

    async def cleanup(self, limit: int = 32) -> int:
        """Repeat tombstone cleanup; a late stale write is deleted on a later pass.

        Never remove a referenced blob. Journal rows survive failed deletion and
        remain after successful deletion to catch delayed abandoned writers.
        """
        if not 1 <= limit <= 200:
            raise ValueError("Invalid cleanup batch")
        async with self.queue.transaction(write=False) as session:
            now = await self.queue.now(session)
            rows = list(
                (
                    await session.scalars(
                        select(SourceRefreshBlob)
                        .where(
                            SourceRefreshBlob.published.is_(False),
                            SourceRefreshBlob.next_cleanup_at <= now,
                        )
                        .order_by(SourceRefreshBlob.next_cleanup_at, SourceRefreshBlob.id)
                        .limit(limit)
                    )
                ).all()
            )
        count = 0
        for row in rows:
            async with self.queue.transaction() as session:
                # The publication deadline precedes this GC deadline. Locking the
                # run's source/lease before the blob avoids publish/delete races.
                from ezo_api.db.models import SourceRefreshRun

                run = await session.get(SourceRefreshRun, row.run_id) if row.run_id else None
                if run is not None:
                    # GC has no user-facing read authority. Lock the source for
                    # publication ordering, but do not let an inconsistent library
                    # ownership link block unrelated orphan cleanup forever.
                    await session.scalar(
                        select(LearnedSource.id)
                        .where(LearnedSource.id == run.source_id)
                        .with_for_update()
                    )
                blob = await session.scalar(
                    select(SourceRefreshBlob)
                    .where(SourceRefreshBlob.id == row.id)
                    .with_for_update()
                )
                if (
                    blob is None
                    or blob.published
                    or blob.next_cleanup_at > await self.queue.now(session)
                ):
                    continue
                used = await session.scalar(
                    select(
                        or_(
                            exists().where(KnowledgeDocument.storage_key == blob.storage_key),
                            exists().where(DocumentRevision.storage_key == blob.storage_key),
                        )
                    )
                )
                if used:
                    blob.published = True
                    continue
                # External delete is bounded by the StorageProvider. This GC
                # transaction holds source/blob locks, never a parser/provider call.
                try:
                    await self.learning.knowledge.storage.delete(blob.storage_key)
                except StorageError:
                    blob.next_cleanup_at = now + timedelta(minutes=5)
                    continue
                blob.next_cleanup_at = now + timedelta(days=1)
                count += 1
        return count
