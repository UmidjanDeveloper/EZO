"""Durable, permission-fenced source refresh. No generated code or native executor.

Lock order: source -> policy -> optional owner quota row -> run -> ordered documents.
Fetch/parse/embed/blob writes happen outside publication's SQL transaction. The
manifest, documents, revisions, vectors, source metadata and run finalize together.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import (
    KnowledgeDocument,
    KnowledgeLibrary,
    KnowledgeSource,
    LearnedSource,
    Project,
    SourceRefreshBlob,
    SourceRefreshPolicy,
    SourceRefreshRun,
    User,
)
from ezo_api.db.session import Database
from ezo_api.knowledge.jobs.service import JobError
from ezo_api.learning.base import Limits
from ezo_api.security.audit import audit

ACTIVE = ("queued", "running")
MAX_RUNS_PER_USER = 10_000


class _InputDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: uuid.UUID | None
    status: str = Field(min_length=1, max_length=20)
    project_id: uuid.UUID | None
    updated: AwareDatetime


class _InputSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["source-refresh-input/v1"]
    project_id: uuid.UUID | None
    kind: Literal["website", "github", "pypi", "npm"]
    target: str = Field(min_length=1, max_length=1000)
    title: str = Field(max_length=300)
    limits: Limits
    knowledge_source_id: uuid.UUID
    documents: list[_InputDocument] = Field(max_length=200)


def run_out(run: SourceRefreshRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "source_id": str(run.source_id),
        "request_id": str(run.request_id),
        "generation": run.generation,
        "state": run.state,
        "attempts": run.attempts,
        "max_attempts": 3,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error_code": run.error_code,
        "result": run.result,
    }


def fingerprint(rows: list[KnowledgeDocument]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(d.id),
            "hash": d.content_hash,
            "revision": str(d.current_revision_id) if d.current_revision_id else None,
            "status": d.status,
            "project_id": str(d.project_id) if d.project_id else None,
            "updated": d.updated_at.isoformat(),
        }
        for d in sorted(rows, key=lambda d: d.id)
    ]


@dataclass(frozen=True)
class RefreshLease:
    run_id: uuid.UUID
    source_id: uuid.UUID
    user_id: uuid.UUID
    token: uuid.UUID
    generation: int
    attempt: int
    expires_at: datetime
    input: dict[str, Any]


class RefreshQueue:
    def __init__(self, db: Database) -> None:
        self.db = db

    @asynccontextmanager
    async def transaction(self, *, write: bool = True) -> AsyncIterator[AsyncSession]:
        async with self.db.sessionmaker() as session:
            if write and self.db.engine.dialect.name == "sqlite":
                await session.execute(text("BEGIN IMMEDIATE"))
            else:
                await session.begin()
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def now(self, session: AsyncSession) -> datetime:
        clock = (
            func.clock_timestamp()
            if self.db.engine.dialect.name == "postgresql"
            else func.current_timestamp()
        )
        value = await session.scalar(select(clock))
        assert isinstance(value, datetime)
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    async def source(
        self,
        session: AsyncSession,
        user: uuid.UUID,
        source_id: uuid.UUID,
        *,
        skip_locked: bool = False,
    ) -> LearnedSource:
        source = await session.scalar(
            select(LearnedSource)
            .where(LearnedSource.id == source_id, LearnedSource.user_id == user)
            .with_for_update(skip_locked=skip_locked)
            .execution_options(populate_existing=True)
        )
        if source is None:
            raise JobError("not_found", "Source not found.", 404)
        library = await session.get(KnowledgeLibrary, source.library_id)
        knowledge = await session.get(KnowledgeSource, source.knowledge_source_id)
        if (
            library is None
            or knowledge is None
            or library.user_id != user
            or knowledge.user_id != user
        ):
            raise JobError("scope_mismatch", "Source ownership is inconsistent.", 409)
        if (
            knowledge.project_id is not None
            and await session.scalar(
                select(Project.id).where(
                    Project.id == knowledge.project_id, Project.user_id == user
                )
            )
            is None
        ):
            raise JobError("scope_mismatch", "Source project ownership is inconsistent.")
        return source

    async def policy(
        self, session: AsyncSession, source: LearnedSource, *, create: bool = False
    ) -> SourceRefreshPolicy:
        policy = await session.scalar(
            select(SourceRefreshPolicy)
            .where(SourceRefreshPolicy.source_id == source.id)
            .with_for_update()
        )
        if policy is None:
            if not create:
                raise JobError("permission_required", "Explicit refresh permission is required.")
            # Do not race a legacy initial read, which has no permission fence.
            if source.status in ("queued", "inspecting", "reading", "indexing"):
                raise JobError("busy", "Wait for the initial source read before enabling refresh.")
            policy = SourceRefreshPolicy(
                source_id=source.id, user_id=source.user_id, generation=1, enabled=True
            )
            session.add(policy)
            await session.flush()
        if policy.user_id != source.user_id:
            raise JobError("scope_mismatch", "Source ownership is inconsistent.")
        return policy

    @staticmethod
    def terminal(
        run: SourceRefreshRun, state: str, now: datetime, error: str | None = None
    ) -> None:
        run.state, run.finished_at, run.error_code = state, now, error
        run.active_key = None
        run.lease_token = None
        run.lease_until = None

    async def restore_status(self, session: AsyncSession, source: LearnedSource) -> None:
        statuses = set(
            (
                await session.scalars(
                    select(KnowledgeDocument.status).where(
                        KnowledgeDocument.source_id == source.knowledge_source_id,
                        KnowledgeDocument.status != "removed",
                    )
                )
            ).all()
        )
        source.status = (
            "indexed"
            if statuses == {"indexed"}
            else "partial"
            if statuses & {"indexed", "partial"}
            else "failed"
        )

    async def configure(
        self, user: uuid.UUID, source_id: uuid.UUID, *, enabled: bool, interval_seconds: int | None
    ) -> dict[str, Any]:
        if interval_seconds is not None and not 3600 <= interval_seconds <= 2_592_000:
            raise JobError(
                "invalid_interval", "Schedule interval must be one hour to 30 days.", 422
            )
        if not enabled and interval_seconds is not None:
            raise JobError("invalid_interval", "A revoked source cannot have a schedule.", 422)
        async with self.transaction() as session:
            source = await self.source(session, user, source_id)
            policy = await self.policy(session, source, create=True)
            now = await self.now(session)
            changed = policy.enabled != enabled or policy.interval_seconds != interval_seconds
            if changed:
                policy.generation += 1
                policy.enabled, policy.interval_seconds = enabled, interval_seconds
                run = await session.scalar(
                    select(SourceRefreshRun)
                    .where(
                        SourceRefreshRun.source_id == source_id, SourceRefreshRun.state.in_(ACTIVE)
                    )
                    .with_for_update()
                )
                if run is not None:
                    self.terminal(run, "cancelled", now, "permission_changed")
                    await self.restore_status(session, source)
            if changed or policy.next_run_at is None:
                policy.next_run_at = (
                    now + timedelta(seconds=interval_seconds) if interval_seconds else None
                )
            source.profile = {
                **(source.profile or {}),
                "refresh_fetch_allowed": enabled,
                "refresh_generation": policy.generation,
            }
            audit(
                session,
                user,
                "learning.refresh_permission",
                "learned_source",
                source_id,
                {
                    "enabled": enabled,
                    "generation": policy.generation,
                    "interval_seconds": interval_seconds,
                },
            )
            return {
                "enabled": policy.enabled,
                "generation": policy.generation,
                "interval_seconds": policy.interval_seconds,
                "next_run_at": policy.next_run_at.isoformat() if policy.next_run_at else None,
            }

    async def _enqueue(
        self,
        session: AsyncSession,
        source: LearnedSource,
        policy: SourceRefreshPolicy,
        request_id: uuid.UUID,
    ) -> SourceRefreshRun:
        prior = await session.scalar(
            select(SourceRefreshRun).where(
                SourceRefreshRun.source_id == source.id, SourceRefreshRun.request_id == request_id
            )
        )
        if prior is not None:
            return prior
        if not policy.enabled:
            raise JobError("permission_revoked", "Source refresh permission is revoked.")
        active = await session.scalar(
            select(SourceRefreshRun).where(SourceRefreshRun.active_key == str(source.id))
        )
        if active is not None:
            raise JobError("busy", "A refresh run is already queued or running.")
        # Serialize quota admission for this owner across different sources.
        # All enqueue callers hold only this source's locks at this point.
        owner = await session.scalar(
            select(User.id).where(User.id == source.user_id).with_for_update()
        )
        if owner is None:
            raise JobError("not_found", "Owner not found.", 404)
        count = await session.scalar(
            select(func.count())
            .select_from(SourceRefreshRun)
            .where(SourceRefreshRun.user_id == source.user_id)
        )
        if count is not None and count >= MAX_RUNS_PER_USER:
            raise JobError("history_limit", "Refresh history capacity reached; contact the owner.")
        now = await self.now(session)
        docs = list(
            (
                await session.scalars(
                    select(KnowledgeDocument)
                    .where(
                        KnowledgeDocument.source_id == source.knowledge_source_id,
                        KnowledgeDocument.status != "removed",
                    )
                    .order_by(KnowledgeDocument.id)
                    .limit(201)
                )
            ).all()
        )
        if len(docs) > 200:
            raise JobError(
                "resource_limit", "Refresh supports at most 200 active source documents."
            )
        knowledge_source = await session.get(KnowledgeSource, source.knowledge_source_id)
        assert knowledge_source is not None
        if any(
            d.user_id != source.user_id or d.project_id != knowledge_source.project_id for d in docs
        ):
            raise JobError("scope_mismatch", "Source document ownership is inconsistent.")
        # Original source limits are immutable for this run, not model supplied.
        snapshot = {
            "schema_version": "source-refresh-input/v1",
            "project_id": str(knowledge_source.project_id) if knowledge_source.project_id else None,
            "kind": source.kind,
            "target": source.target,
            "title": source.title,
            "limits": Limits.model_validate(source.limits or {}).model_dump(),
            "knowledge_source_id": str(source.knowledge_source_id),
            "documents": fingerprint(docs),
        }
        run = SourceRefreshRun(
            source_id=source.id,
            user_id=source.user_id,
            request_id=request_id,
            active_key=str(source.id),
            generation=policy.generation,
            state="queued",
            attempts=0,
            input=snapshot,
            available_at=now,
            created_at=now,
        )
        session.add(run)
        source.status, source.error = "queued", None
        await session.flush()
        audit(
            session,
            source.user_id,
            "learning.refresh_enqueue",
            "source_refresh_run",
            run.id,
            {"source_id": str(source.id), "generation": policy.generation},
        )
        return run

    async def enqueue(
        self, user: uuid.UUID, source_id: uuid.UUID, request_id: uuid.UUID
    ) -> dict[str, Any]:
        async with self.transaction() as session:
            source = await self.source(session, user, source_id)
            policy = await self.policy(session, source, create=True)
            return run_out(await self._enqueue(session, source, policy, request_id))

    async def cancel(
        self, user: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> dict[str, Any]:
        async with self.transaction() as session:
            source = await self.source(session, user, source_id)
            run = await session.scalar(
                select(SourceRefreshRun)
                .where(
                    SourceRefreshRun.id == run_id,
                    SourceRefreshRun.source_id == source_id,
                    SourceRefreshRun.user_id == user,
                )
                .with_for_update()
            )
            if run is None:
                raise JobError("not_found", "Refresh run not found.", 404)
            if run.state in ACTIVE:
                self.terminal(run, "cancelled", await self.now(session), "owner_cancelled")
                await self.restore_status(session, source)
                audit(session, user, "learning.refresh_cancel", "source_refresh_run", run.id, {})
            return run_out(run)

    async def schedule_due(self, limit: int = 16) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("Invalid schedule batch size")
        created = 0
        async with self.transaction(write=False) as session:
            now = await self.now(session)
            candidates = (
                await session.execute(
                    select(LearnedSource.id, LearnedSource.user_id)
                    .join(SourceRefreshPolicy, SourceRefreshPolicy.source_id == LearnedSource.id)
                    .where(
                        SourceRefreshPolicy.enabled.is_(True),
                        SourceRefreshPolicy.interval_seconds.is_not(None),
                        SourceRefreshPolicy.next_run_at <= now,
                    )
                    .order_by(SourceRefreshPolicy.next_run_at, LearnedSource.id)
                    .limit(limit)
                )
            ).all()
        # One source per transaction: don't retain locks for several owners while
        # enforcing each owner's quota. Concurrent schedulers recheck the due time.
        for source_id, user_id in candidates:
            async with self.transaction() as session:
                try:
                    async with session.begin_nested():
                        source = await self.source(session, user_id, source_id, skip_locked=True)
                        policy = await self.policy(session, source)
                        now = await self.now(session)
                        if (
                            not policy.enabled
                            or not policy.interval_seconds
                            or not policy.next_run_at
                            or policy.next_run_at > now
                        ):
                            continue
                        active = await session.scalar(
                            select(SourceRefreshRun.id).where(
                                SourceRefreshRun.active_key == str(source.id)
                            )
                        )
                        if active is None:
                            await self._enqueue(session, source, policy, uuid.uuid4())
                            created += 1
                        policy.next_run_at = now + timedelta(seconds=policy.interval_seconds)
                except JobError as exc:
                    if exc.code == "not_found":
                        continue  # deleted or SKIP LOCKED by another scheduler
                    audit(
                        session,
                        user_id,
                        "learning.schedule_blocked",
                        "learned_source",
                        source_id,
                        {"code": exc.code},
                    )
                    blocked_policy = await session.scalar(
                        select(SourceRefreshPolicy).where(
                            SourceRefreshPolicy.source_id == source_id
                        )
                    )
                    if blocked_policy:
                        blocked_policy.next_run_at = await self.now(session) + timedelta(hours=24)
        return created

    async def claim(self) -> RefreshLease | None:
        async with self.transaction() as session:
            now = await self.now(session)
            # Lock both rows in one SKIP LOCKED selection; a locked source must not
            # block a worker behind it. SQLite serializes at BEGIN IMMEDIATE.
            candidates = (
                await session.execute(
                    select(LearnedSource, SourceRefreshRun)
                    .join(SourceRefreshRun, SourceRefreshRun.source_id == LearnedSource.id)
                    .where(
                        or_(
                            (SourceRefreshRun.state == "queued")
                            & (SourceRefreshRun.available_at <= now),
                            (SourceRefreshRun.state == "running")
                            & (SourceRefreshRun.lease_until <= now),
                        )
                    )
                    .order_by(SourceRefreshRun.created_at, SourceRefreshRun.id)
                    .with_for_update(skip_locked=True, of=(LearnedSource, SourceRefreshRun))
                    .limit(16)
                )
            ).all()
            for source, run in candidates:
                try:
                    await self.source(session, run.user_id, source.id)
                    policy = await self.policy(session, source)
                except JobError:
                    self.terminal(run, "failed", now, "scope_mismatch")
                    continue
                try:
                    _InputSnapshot.model_validate(run.input)
                except ValidationError:
                    self.terminal(run, "failed", now, "invalid_snapshot")
                    await self.restore_status(session, source)
                    continue
                if (
                    run.input.get("knowledge_source_id") != str(source.knowledge_source_id)
                    or run.input.get("kind") != source.kind
                    or run.input.get("target") != source.target
                ):
                    self.terminal(run, "failed", now, "input_mismatch")
                    await self.restore_status(session, source)
                    continue
                if not policy.enabled or policy.generation != run.generation:
                    self.terminal(run, "cancelled", now, "permission_changed")
                    await self.restore_status(session, source)
                    continue
                if run.attempts >= 3:
                    self.terminal(run, "failed", now, "attempts_exhausted")
                    await self.restore_status(session, source)
                    continue
                run.attempts += 1
                run.state, run.lease_token = "running", uuid.uuid4()
                # Fixed whole-run deadline, no heartbeat can extend an attempt forever.
                seconds = Limits.model_validate(run.input["limits"]).max_seconds
                run.lease_until = now + timedelta(seconds=seconds + 30)
                source.status = "reading"
                audit(
                    session,
                    run.user_id,
                    "learning.refresh_claim",
                    "source_refresh_run",
                    run.id,
                    {"attempt": run.attempts, "generation": run.generation},
                )
                return RefreshLease(
                    run.id,
                    source.id,
                    run.user_id,
                    run.lease_token,
                    run.generation,
                    run.attempts,
                    run.lease_until,
                    run.input,
                )
        return None

    async def fence(
        self, session: AsyncSession, lease: RefreshLease
    ) -> tuple[LearnedSource, SourceRefreshRun]:
        source = await self.source(session, lease.user_id, lease.source_id)
        policy = await self.policy(session, source)
        run = await session.scalar(
            select(SourceRefreshRun).where(SourceRefreshRun.id == lease.run_id).with_for_update()
        )
        now = await self.now(session)
        if (
            run is None
            or run.state != "running"
            or run.lease_token != lease.token
            or run.attempts != lease.attempt
            or run.user_id != lease.user_id
            or run.source_id != lease.source_id
            or run.generation != lease.generation
            or not run.lease_until
            or run.lease_until <= now
            or not policy.enabled
            or policy.generation != lease.generation
        ):
            raise JobError(
                "stale_lease", "This refresh attempt no longer has publication authority."
            )
        return source, run

    async def check(self, lease: RefreshLease) -> None:
        async with self.transaction() as session:
            await self.fence(session, lease)

    async def journal(self, lease: RefreshLease, key: str) -> None:
        async with self.transaction() as session:
            await self.fence(session, lease)
            session.add(
                SourceRefreshBlob(
                    run_id=lease.run_id,
                    storage_key=key,
                    published=False,
                    next_cleanup_at=lease.expires_at + timedelta(minutes=1),
                )
            )

    async def fail(self, lease: RefreshLease, code: str, *, transient: bool = False) -> None:
        async with self.transaction() as session:
            source, run = await self.fence(session, lease)
            now = await self.now(session)
            if transient and run.attempts < 3:
                run.state, run.lease_token, run.lease_until = "queued", None, None
                run.available_at, run.error_code = now + timedelta(seconds=30), code
                source.status = "queued"
            else:
                self.terminal(run, "failed", now, code)
                await self.restore_status(session, source)
            audit(
                session,
                lease.user_id,
                "learning.refresh_failure",
                "source_refresh_run",
                run.id,
                {"code": code, "state": run.state, "attempt": run.attempts},
            )
