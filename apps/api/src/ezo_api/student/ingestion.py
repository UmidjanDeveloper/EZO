"""Raw input → fenced publication and K1/K2 chunks, in short DB transactions.

The API only stores bytes. Parsing happens exclusively in the isolated worker.
No mutable object-store pointer is used as an executable input revision.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Literal, cast

from sqlalchemy import func, select

from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DocumentJob,
    DocumentJobPublication,
    DocumentRevision,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    Project,
    StudentRawRevision,
)
from ezo_api.db.session import Database
from ezo_api.documents.executor.protocol import (
    MAX_INPUT_BYTES,
    PROCESSOR_VERSION,
    ExtractionResult,
)
from ezo_api.knowledge.jobs.service import DocumentJobs, JobError, Lease
from ezo_api.knowledge.uploads import sanitize_filename

NativeFormat = Literal["pdf", "docx", "epub"]


class StudentIngestion(DocumentJobs):
    def __init__(self, db: Database, *, lease_seconds: int = 120) -> None:
        super().__init__(db, lease_seconds=lease_seconds, parser_version=PROCESSOR_VERSION)

    async def submit_raw(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        filename: str,
        data: bytes,
    ) -> DocumentJob:
        filename = sanitize_filename(filename)
        format = filename.rsplit(".", 1)[-1].lower()
        if format not in ("pdf", "docx", "epub"):
            raise JobError("unsupported_format", "Use PDF, DOCX or EPUB.", 422)
        if not data or len(data) > MAX_INPUT_BYTES:
            raise JobError("input_limit", "Document must be between 1 byte and 5 MiB.", 422)
        # Only fixed signatures here; archive/XML inspection belongs in the cgroup.
        if not data.startswith(b"%PDF-" if format == "pdf" else b"PK"):
            raise JobError("invalid_input", "The document signature is invalid.", 422)
        digest = hashlib.sha256(data).hexdigest()
        async with self._transaction() as session:
            # Serialize same-owner registration and deduplication, including null scope.
            # A user row exists after authentication; no lock spans native work.
            from ezo_api.db.models import User

            await session.scalar(select(User.id).where(User.id == user_id).with_for_update())
            if (
                project_id is not None
                and await session.scalar(
                    select(Project.id).where(Project.id == project_id, Project.user_id == user_id)
                )
                is None
            ):
                raise JobError("not_found", "Project not found.", 404)
            existing = await session.scalar(
                select(DocumentJob)
                .join(KnowledgeDocument)
                .where(
                    KnowledgeDocument.user_id == user_id,
                    KnowledgeDocument.project_id.is_not_distinct_from(project_id),
                    KnowledgeDocument.content_hash == digest,
                    DocumentJob.parser_version == PROCESSOR_VERSION,
                )
                .order_by(DocumentJob.created_at.desc(), DocumentJob.id.desc())
                .limit(1)
            )
            if existing is not None:
                return existing
            source = KnowledgeSource(
                user_id=user_id, project_id=project_id, name=filename, source_type="upload"
            )
            session.add(source)
            await session.flush()
            doc = KnowledgeDocument(
                user_id=user_id,
                project_id=project_id,
                source_id=source.id,
                title=filename,
                filename=filename,
                mime_type={
                    "pdf": "application/pdf",
                    "epub": "application/epub+zip",
                    "docx": (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ),
                }[format],
                size_bytes=len(data),
                content_hash=digest,
                status="queued",
                meta={"student": True},
            )
            session.add(doc)
            await session.flush()
            revision = DocumentRevision(
                document_id=doc.id,
                revision_number=1,
                content_hash=digest,
                raw_text="",
                meta={"raw_format": format},
            )
            session.add(revision)
            await session.flush()
            session.add(
                StudentRawRevision(revision_id=revision.id, data=data, format=format, sha256=digest)
            )
            job = DocumentJob(
                user_id=user_id,
                project_id=project_id,
                document_id=doc.id,
                input_revision_id=revision.id,
                input_content_hash=digest,
                input_text_sha256=hashlib.sha256(b"").hexdigest(),
                parser_version=PROCESSOR_VERSION,
                max_attempts=3,
                available_at=await self._now(session),
            )
            session.add(job)
            await session.flush()
            return job

    async def raw_input(self, lease: Lease) -> tuple[bytes, NativeFormat]:
        async with self._transaction() as session:
            job = await self._leased(session, lease)
            raw = await session.get(StudentRawRevision, job.input_revision_id)
            if (
                raw is None
                or raw.sha256 != job.input_content_hash
                or hashlib.sha256(raw.data).hexdigest() != raw.sha256
            ):
                raise JobError("revision_conflict", "The immutable source does not match.")
            return raw.data, cast(NativeFormat, raw.format)

    async def publish_extraction(self, lease: Lease, result: ExtractionResult) -> None:
        if not result.text.strip() or result.needs_ocr:
            raise JobError(
                "ocr_required", "Readable text was not available; OCR is not supported.", 422
            )
        # The parser's exact NFC Unicode offsets are authoritative. Do not re-normalize
        # whitespace and thereby move citations after extraction.
        digest = hashlib.sha256(result.model_dump_json().encode()).hexdigest()
        text_hash = hashlib.sha256(result.text.encode()).hexdigest()
        async with self._transaction() as session:
            job = await self._leased(session, lease, allow_completed=True)
            if (
                job.parser_version != PROCESSOR_VERSION
                or result.source_sha256 != job.input_content_hash
            ):
                raise JobError("revision_conflict", "Extraction does not match the pinned input.")
            existing = await session.scalar(
                select(DocumentJobPublication).where(DocumentJobPublication.job_id == job.id)
            )
            if existing is not None:
                if existing.result_sha256 != digest:
                    raise JobError("publication_conflict", "Publication already exists.")
                return
            raw = await session.get(StudentRawRevision, job.input_revision_id)
            if raw is None or hashlib.sha256(raw.data).hexdigest() != result.source_sha256:
                raise JobError("revision_conflict", "The immutable source does not match.")
            doc = await self._document(session, job.user_id, job.project_id, job.document_id)
            number = await session.scalar(
                select(func.max(DocumentRevision.revision_number)).where(
                    DocumentRevision.document_id == doc.id
                )
            )
            output = DocumentRevision(
                document_id=doc.id,
                revision_number=(number or 0) + 1,
                content_hash=text_hash,
                raw_text=result.text,
                meta={
                    "input_revision_id": str(job.input_revision_id),
                    "source_sha256": result.source_sha256,
                    "sections": [s.model_dump() for s in result.sections],
                },
            )
            session.add(output)
            await session.flush()
            # Bounded exact slices preserve global offsets, with no page invention.
            chunks: list[KnowledgeChunk] = []
            for section in result.sections:
                for start in range(section.start, section.end, 1200):
                    end = min(start + 1200, section.end)
                    chunks.append(
                        KnowledgeChunk(
                            user_id=job.user_id,
                            document_id=doc.id,
                            revision_id=output.id,
                            chunk_index=len(chunks),
                            text=result.text[start:end],
                            meta={
                                "start": start,
                                "end": end,
                                "page_start": section.page,
                                "page_end": section.page,
                                "heading": section.heading,
                                "member": section.member,
                                "source_sha256": result.source_sha256,
                            },
                        )
                    )
            if not chunks or len(chunks) > 3000:
                raise JobError(
                    "resource_limit", "The document structure exceeds the index budget.", 422
                )
            session.add_all(chunks)
            session.add(
                DocumentJobPublication(
                    job_id=job.id,
                    input_revision_id=job.input_revision_id,
                    parser_version=PROCESSOR_VERSION,
                    normalized_text=result.text,
                    text_sha256=text_hash,
                    result_sha256=digest,
                    spans=[{"start": s.start, "end": s.end} for s in result.sections],
                )
            )
            await self._leased(session, lease)
            doc.current_revision_id, doc.status = output.id, "indexed"
            doc.chunk_count, doc.indexed_at = len(chunks), utcnow()
            job.state, job.lease_expires_at = "completed", None
            await session.flush()

    async def defer_admission(self, lease: Lease) -> None:
        """An atomic Docker-slot rejection started no workload; do not spend a retry.

        Revoke the token before refunding this *unadmitted* claim. Never called
        for an uncertain daemon failure or a workload that started execution.
        """
        async with self._transaction() as session:
            job = await self._leased(session, lease)
            job.state = "queued"
            job.attempts -= 1
            job.lease_token = job.lease_expires_at = job.worker_id = None
            job.available_at = await self._now(session) + timedelta(seconds=2)

    async def retry(
        self, user_id: uuid.UUID, project_id: uuid.UUID | None, job_id: uuid.UUID
    ) -> DocumentJob:
        """Explicit new generation; at most 3 generations/3 attempts per document.

        Repeating a request on an old generation returns the existing successor.
        Completed results and terminal history are never overwritten or revived.
        """
        async with self._transaction() as session:
            old = await self._job(session, user_id, project_id, job_id, lock=True)
            if old.parser_version != PROCESSOR_VERSION or old.state not in ("failed", "cancelled"):
                raise JobError("retry_unavailable", "Only terminal native jobs can be retried.")
            jobs = list(
                (
                    await session.scalars(
                        select(DocumentJob)
                        .where(
                            DocumentJob.document_id == old.document_id,
                            DocumentJob.parser_version == PROCESSOR_VERSION,
                        )
                        .order_by(DocumentJob.created_at, DocumentJob.id)
                    )
                ).all()
            )
            for candidate in jobs:
                revision = await session.get(DocumentRevision, candidate.input_revision_id)
                if revision is not None and revision.meta.get("retry_of") == str(old.id):
                    return candidate
            spent = sum(j.attempts for j in jobs)
            if len(jobs) >= 3 or spent >= 3:
                raise JobError("attempts_exhausted", "The lifetime retry budget was reached.")
            raw = await session.get(StudentRawRevision, old.input_revision_id)
            if raw is None:
                raise JobError("not_found", "Source no longer exists.", 404)
            number = await session.scalar(
                select(func.max(DocumentRevision.revision_number)).where(
                    DocumentRevision.document_id == old.document_id
                )
            )
            rev = DocumentRevision(
                document_id=old.document_id,
                revision_number=(number or 0) + 1,
                content_hash=raw.sha256,
                raw_text="",
                meta={"retry_of": str(old.id)},
            )
            session.add(rev)
            await session.flush()
            session.add(
                StudentRawRevision(
                    revision_id=rev.id, data=raw.data, format=raw.format, sha256=raw.sha256
                )
            )
            job = DocumentJob(
                user_id=user_id,
                project_id=project_id,
                document_id=old.document_id,
                input_revision_id=rev.id,
                input_content_hash=raw.sha256,
                input_text_sha256=hashlib.sha256(b"").hexdigest(),
                parser_version=PROCESSOR_VERSION,
                max_attempts=3 - spent,
                available_at=await self._now(session),
            )
            session.add(job)
            await session.flush()
            return job
