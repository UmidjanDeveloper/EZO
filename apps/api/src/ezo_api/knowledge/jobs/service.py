"""Short durable transactions, fenced leases and immutable stored-text publications.

The only current processor contract copies an existing normalized revision. No
native parser, provider, network, arbitrary callback or worker daemon lives here.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, get_args

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import (
    DocumentJob,
    DocumentJobPublication,
    DocumentRevision,
    KnowledgeDocument,
    Project,
)
from ezo_api.db.session import Database
from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.schemas.document_jobs import CitationSpan, PublicationOut

PARSER_VERSION = "stored-normalized-text/v1"
MAX_TEXT_CHARS = 2_000_000
MAX_SPANS = 1000
ERRORS = {
    "transient": "Processing was interrupted; a bounded retry may be scheduled.",
    "invalid_input": "The document cannot be processed by this processor version.",
    "resource_limit": "The document exceeded the processing resource budget.",
    "internal_error": "Processing failed. Contact the owner with the job identifier.",
    "attempts_exhausted": "The processing attempt limit was reached.",
    "ocr_required": "No readable text layer; retry with OCR languages to read it as a scan.",
    "ocr_incomplete": (
        "OCR could not read this scan within the isolated limits "
        "(page count, time or installed languages)."
    ),
}
FailCode = Literal[
    "transient",
    "invalid_input",
    "resource_limit",
    "internal_error",
    "ocr_required",
    "ocr_incomplete",
]


class JobError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


@dataclass(frozen=True)
class Lease:
    job_id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None
    token: uuid.UUID
    attempt: int
    input_revision_id: uuid.UUID
    parser_version: str


class DocumentJobs:
    def __init__(
        self,
        db: Database,
        *,
        lease_seconds: int = 60,
        max_attempts: int = 3,
        parser_version: str | None = None,
    ) -> None:
        if not 5 <= lease_seconds <= 300:
            raise ValueError("Lease duration must be from 5 to 300 seconds")
        if not 1 <= max_attempts <= 5:
            raise ValueError("Attempt limit must be from 1 to 5")
        if parser_version not in (None, PARSER_VERSION, "isolated-extraction/v1"):
            raise ValueError("Unsupported processor version")
        self._parser_version = parser_version
        self.max_attempts = max_attempts
        self.db = db
        self.lease_seconds = lease_seconds

    @property
    def parser_version(self) -> str:
        return self._parser_version or PARSER_VERSION

    @asynccontextmanager
    async def _transaction(self, *, write: bool = True) -> AsyncIterator[AsyncSession]:
        # Dedicated session: auth's read transaction never gets upgraded mid-request.
        async with self.db.sessionmaker() as session:
            if write and self.db.engine.dialect.name == "sqlite":
                # Development contract: one worker. Serialize writers before selection;
                # do not pretend SQLite implements PostgreSQL's SKIP LOCKED.
                await session.execute(text("BEGIN IMMEDIATE"))
            else:
                await session.begin()
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def _now(self, session: AsyncSession) -> datetime:
        # PostgreSQL transaction timestamps can be stale after waiting for a lock.
        clock = (
            func.clock_timestamp()
            if self.db.engine.dialect.name == "postgresql"
            else func.current_timestamp()
        )
        with session.no_autoflush:
            now = await session.scalar(select(clock))
        assert isinstance(now, datetime)
        return now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)

    async def _document(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        document_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> KnowledgeDocument:
        query = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.user_id == user_id,
            KnowledgeDocument.project_id.is_not_distinct_from(project_id),
        )
        if lock:
            query = query.with_for_update()
        doc = await session.scalar(query.execution_options(populate_existing=True))
        project = await session.get(Project, project_id) if project_id else None
        if doc is None or (
            project_id is not None and (project is None or project.user_id != user_id)
        ):
            raise JobError("not_found", "Document or job not found.", 404)
        return doc

    async def _job(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        job_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> DocumentJob:
        query = select(DocumentJob).where(
            DocumentJob.id == job_id,
            DocumentJob.user_id == user_id,
            DocumentJob.project_id.is_not_distinct_from(project_id),
        )
        job = await session.scalar(query)
        if job is None:
            raise JobError("not_found", "Document or job not found.", 404)
        # All mutators lock document first, then job. Cancellation/publication serialize.
        await self._document(session, user_id, project_id, job.document_id, lock=lock)
        if lock:
            job = await session.scalar(
                query.with_for_update().execution_options(populate_existing=True)
            )
            if job is None:
                raise JobError("not_found", "Document or job not found.", 404)
        return job

    async def enqueue(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        document_id: uuid.UUID,
        revision_id: uuid.UUID,
    ) -> DocumentJob:
        async with self._transaction() as session:
            await self._document(session, user_id, project_id, document_id, lock=True)
            revision = await session.scalar(
                select(DocumentRevision).where(
                    DocumentRevision.id == revision_id,
                    DocumentRevision.document_id == document_id,
                    func.length(DocumentRevision.raw_text) <= MAX_TEXT_CHARS,
                )
            )
            if revision is None:
                exists = await session.scalar(
                    select(DocumentRevision.id).where(
                        DocumentRevision.id == revision_id,
                        DocumentRevision.document_id == document_id,
                    )
                )
                if exists is not None:
                    raise JobError("resource_limit", ERRORS["resource_limit"], 422)
                raise JobError("not_found", "Document or job not found.", 404)
            if len(revision.raw_text) > MAX_TEXT_CHARS:
                raise JobError("resource_limit", ERRORS["resource_limit"], 422)
            text_hash = hashlib.sha256(revision.raw_text.encode()).hexdigest()
            existing = await session.scalar(
                select(DocumentJob).where(
                    DocumentJob.document_id == document_id,
                    DocumentJob.input_revision_id == revision_id,
                    DocumentJob.parser_version == self.parser_version,
                )
            )
            if existing:
                if existing.user_id != user_id or existing.project_id != project_id:
                    raise JobError("scope_changed", "The document processing scope has changed.")
                if (
                    existing.input_content_hash != revision.content_hash
                    or existing.input_text_sha256 != text_hash
                ):
                    raise JobError("revision_conflict", "The pinned input revision has changed.")
                return existing
            job = DocumentJob(
                user_id=user_id,
                project_id=project_id,
                document_id=document_id,
                input_revision_id=revision_id,
                input_content_hash=revision.content_hash,
                input_text_sha256=text_hash,
                parser_version=self.parser_version,
                max_attempts=self.max_attempts,
                available_at=await self._now(session),
            )
            session.add(job)
            await session.flush()
            return job

    async def get(
        self, user_id: uuid.UUID, project_id: uuid.UUID | None, job_id: uuid.UUID
    ) -> DocumentJob:
        async with self._transaction(write=False) as session:
            return await self._job(session, user_id, project_id, job_id)

    async def cancel(
        self, user_id: uuid.UUID, project_id: uuid.UUID | None, job_id: uuid.UUID
    ) -> DocumentJob:
        async with self._transaction() as session:
            job = await self._job(session, user_id, project_id, job_id, lock=True)
            if job.state == "completed":
                raise JobError("already_completed", "A published job cannot be cancelled.")
            if job.state not in ("failed", "cancelled"):
                job.state, job.lease_token, job.lease_expires_at = "cancelled", None, None
                job.worker_id = None
                job.error_code = job.error_message = None
            return job

    async def claim(self, worker_id: str) -> Lease | None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", worker_id):
            raise ValueError("Worker identifier must be 1..80 ASCII identifier characters")
        async with self._transaction() as session:
            for _ in range(100):  # bounded cleanup of expired final attempts per poll
                now = await self._now(session)
                query = (
                    select(DocumentJob)
                    .join(KnowledgeDocument, DocumentJob.document_id == KnowledgeDocument.id)
                    .join(
                        DocumentRevision,
                        and_(
                            DocumentRevision.id == DocumentJob.input_revision_id,
                            DocumentRevision.document_id == DocumentJob.document_id,
                            DocumentRevision.content_hash == DocumentJob.input_content_hash,
                        ),
                    )
                    .where(
                        DocumentJob.parser_version == self.parser_version,
                        DocumentJob.user_id == KnowledgeDocument.user_id,
                        or_(
                            DocumentJob.project_id.is_(None),
                            select(Project.id)
                            .where(
                                Project.id == DocumentJob.project_id,
                                Project.user_id == DocumentJob.user_id,
                            )
                            .exists(),
                        ),
                        DocumentJob.project_id.is_not_distinct_from(KnowledgeDocument.project_id),
                        or_(
                            and_(DocumentJob.state == "queued", DocumentJob.available_at <= now),
                            and_(
                                DocumentJob.state == "running", DocumentJob.lease_expires_at <= now
                            ),
                        ),
                    )
                    .order_by(DocumentJob.available_at, DocumentJob.created_at, DocumentJob.id)
                    .limit(1)
                    .with_for_update(skip_locked=True, of=(KnowledgeDocument, DocumentJob))
                )
                job = await session.scalar(query)
                if job is None:
                    return None
                await self._document(session, job.user_id, job.project_id, job.document_id)
                if job.attempts >= job.max_attempts:
                    job.state, job.lease_token, job.lease_expires_at = "failed", None, None
                    job.error_code, job.error_message = (
                        "attempts_exhausted",
                        ERRORS["attempts_exhausted"],
                    )
                    await session.flush()
                    continue
                job.state = "running"
                job.attempts += 1
                job.lease_token = uuid.uuid4()
                job.worker_id = worker_id
                job.lease_expires_at = (await self._now(session)) + timedelta(
                    seconds=self.lease_seconds
                )
                job.error_code = job.error_message = None
                return Lease(
                    job.id,
                    job.user_id,
                    job.project_id,
                    job.lease_token,
                    job.attempts,
                    job.input_revision_id,
                    job.parser_version,
                )
        return None

    async def _leased(
        self, session: AsyncSession, lease: Lease, *, allow_completed: bool = False
    ) -> DocumentJob:
        job = await self._job(session, lease.user_id, lease.project_id, lease.job_id, lock=True)
        valid = (
            job.lease_token == lease.token
            and job.attempts == lease.attempt
            and job.input_revision_id == lease.input_revision_id
            and job.parser_version == lease.parser_version
        )
        if allow_completed and valid and job.state == "completed":
            return job
        if (
            not valid
            or job.state != "running"
            or job.lease_expires_at is None
            or job.lease_expires_at <= await self._now(session)
        ):
            raise JobError("lease_lost", "The processing lease is no longer valid.")
        return job

    async def heartbeat(self, lease: Lease) -> None:
        async with self._transaction() as session:
            job = await self._leased(session, lease)
            job.lease_expires_at = (await self._now(session)) + timedelta(
                seconds=self.lease_seconds
            )

    async def fail(
        self,
        lease: Lease,
        code: FailCode,
    ) -> None:
        if code not in get_args(FailCode):
            raise ValueError("Unrecognized safe failure category")
        async with self._transaction() as session:
            job = await self._leased(session, lease)
            retry = code == "transient" and job.attempts < job.max_attempts
            job.state = "queued" if retry else "failed"
            job.available_at = (await self._now(session)) + timedelta(
                seconds=min(60, 5 * 2 ** (job.attempts - 1))
            )
            job.error_code, job.error_message = code, ERRORS[code]
            job.lease_token, job.lease_expires_at, job.worker_id = None, None, None

    async def publish(
        self, lease: Lease, normalized_text: str, spans: list[CitationSpan]
    ) -> DocumentJobPublication:
        if self.parser_version != PARSER_VERSION:
            raise JobError("invalid_input", ERRORS["invalid_input"], 422)
        if len(normalized_text) > MAX_TEXT_CHARS or len(spans) > MAX_SPANS:
            raise JobError("resource_limit", ERRORS["resource_limit"], 422)
        if normalize_text(normalized_text) != normalized_text:
            raise JobError("invalid_text", "Publication text must already be normalized.", 422)
        previous = 0
        for span in spans:
            if not previous <= span.start < span.end <= len(normalized_text):
                raise JobError(
                    "invalid_offsets",
                    "Citation spans must be ordered, nonoverlapping text offsets.",
                    422,
                )
            previous = span.end
        canonical_spans = [span.model_dump() for span in spans]
        digest = hashlib.sha256(
            json.dumps(
                {"text": normalized_text, "spans": canonical_spans},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._transaction() as session:
            job = await self._leased(session, lease, allow_completed=True)
            existing = await session.scalar(
                select(DocumentJobPublication).where(DocumentJobPublication.job_id == job.id)
            )
            if existing:
                if existing.result_sha256 != digest:
                    raise JobError(
                        "publication_conflict", "This job already published a different result."
                    )
                return existing
            revision = await session.scalar(
                select(DocumentRevision).where(
                    DocumentRevision.id == job.input_revision_id,
                    func.length(DocumentRevision.raw_text) <= MAX_TEXT_CHARS,
                )
            )
            if (
                revision is None
                or revision.document_id != job.document_id
                or revision.content_hash != job.input_content_hash
                or revision.raw_text != normalized_text
                or job.input_text_sha256 != hashlib.sha256(normalized_text.encode()).hexdigest()
                or job.parser_version != PARSER_VERSION
            ):
                raise JobError(
                    "revision_conflict", "The pinned stored-text revision does not match."
                )
            publication = DocumentJobPublication(
                job_id=job.id,
                input_revision_id=revision.id,
                parser_version=job.parser_version,
                normalized_text=normalized_text,
                text_sha256=hashlib.sha256(normalized_text.encode()).hexdigest(),
                result_sha256=digest,
                spans=canonical_spans,
            )
            session.add(publication)
            # Deadline is checked again after text validation, immediately before writes.
            await self._leased(session, lease)
            job.state, job.lease_expires_at = "completed", None
            await session.flush()
            return publication

    async def result(
        self, user_id: uuid.UUID, project_id: uuid.UUID | None, job_id: uuid.UUID
    ) -> DocumentJobPublication:
        async with self._transaction(write=False) as session:
            job = await self._job(session, user_id, project_id, job_id)
            result = await session.scalar(
                select(DocumentJobPublication).where(DocumentJobPublication.job_id == job.id)
            )
            if job.state != "completed" or result is None:
                raise JobError("result_unavailable", "The job has not published a result.")
            return result

    async def result_page(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        job_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 4000,
    ) -> PublicationOut:
        """Authorized SQL slice; citation offsets remain global and unclipped."""
        if offset < 0 or not 1 <= limit <= 8000:
            raise JobError("invalid_page", "Invalid result page bounds.", 422)
        async with self._transaction(write=False) as session:
            job = await self._job(session, user_id, project_id, job_id)
            if job.state != "completed":
                raise JobError("result_unavailable", "The job has not published a result.")
            # Valid publications are capped at MAX_TEXT_CHARS and MAX_SPANS by publish.
            # Clamp only the SQL argument (not the returned offset) so arbitrarily
            # large out-of-range API offsets never overflow a database integer.
            row = (
                await session.execute(
                    select(
                        DocumentJobPublication.id,
                        DocumentJobPublication.input_revision_id,
                        DocumentJobPublication.parser_version,
                        DocumentJobPublication.text_sha256,
                        func.substr(
                            DocumentJobPublication.normalized_text,
                            min(offset, MAX_TEXT_CHARS) + 1,
                            limit,
                        ).label("text"),
                        func.length(DocumentJobPublication.normalized_text).label("total_chars"),
                        DocumentJobPublication.spans,
                    ).where(DocumentJobPublication.job_id == job.id)
                )
            ).one_or_none()
            if row is None:
                raise JobError("result_unavailable", "The job has not published a result.")
            end = offset + len(row.text)
            return PublicationOut(
                id=row.id,
                input_revision_id=row.input_revision_id,
                parser_version=row.parser_version,
                text_sha256=row.text_sha256,
                text=row.text,
                offset=offset,
                total_chars=row.total_chars,
                spans=[
                    CitationSpan.model_validate(span)
                    for span in row.spans
                    if offset < end and span["start"] < end and span["end"] > offset
                ],
            )

    async def read_input(self, lease: Lease) -> str:
        """Bounded pinned source for the fixed stored-text worker, never a parser."""
        if self.parser_version != PARSER_VERSION:
            raise JobError("invalid_input", ERRORS["invalid_input"], 422)
        async with self._transaction() as session:
            job = await self._leased(session, lease)
            row = (
                await session.execute(
                    select(DocumentRevision.raw_text, DocumentRevision.content_hash).where(
                        DocumentRevision.id == job.input_revision_id,
                        DocumentRevision.document_id == job.document_id,
                        func.length(DocumentRevision.raw_text) <= MAX_TEXT_CHARS,
                    )
                )
            ).one_or_none()
            if row is None or row.content_hash != job.input_content_hash:
                raise JobError("revision_conflict", "The pinned input revision has changed.")
            if hashlib.sha256(row.raw_text.encode()).hexdigest() != job.input_text_sha256:
                raise JobError("revision_conflict", "The pinned input revision has changed.")
            return str(row.raw_text)
