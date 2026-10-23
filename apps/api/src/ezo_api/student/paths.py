"""Explicit source-grounded learning paths, adapting only to real recall evidence.

No model-produced mastery scores, fabricated diagnostic results or review side
effects. Definitions are immutable; pause/delete uses optimistic version fencing.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    KnowledgeDocument,
    PersonalGoal,
    StudentLearningPath,
    StudyCard,
    StudyReview,
    User,
)
from ezo_api.db.session import Database
from ezo_api.knowledge.jobs.service import JobError
from ezo_api.security.audit import audit
from ezo_api.student.study import scope

MAX_ACTIVE_PATHS = 100
MAX_TOTAL_PATHS = 1000


class PathStepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    card_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    prerequisites: list[int] = Field(default_factory=list, max_length=29)
    required_recalls: int = Field(default=1, ge=1, le=5)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a nonblank title.")
        return value.strip()


class LearningPathIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID
    project_id: uuid.UUID | None = None
    goal_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    language: Literal["uz", "en", "ru"] = "uz"
    steps: list[PathStepIn] = Field(min_length=1, max_length=30)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a nonblank title.")
        return value.strip()

    @model_validator(mode="after")
    def bounded_dag(self) -> LearningPathIn:
        cards = [card for step in self.steps for card in step.card_ids]
        if len(cards) > 200 or len(cards) != len(set(cards)):
            raise ValueError("A path supports at most 200 distinct cards, each in one step.")
        for index, step in enumerate(self.steps):
            if len(step.prerequisites) != len(set(step.prerequisites)) or any(
                p < 0 or p >= index for p in step.prerequisites
            ):
                raise ValueError("Prerequisites must be distinct earlier step indexes.")
        return self


class PathStateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID | None = None
    expected_version: int = Field(ge=0, le=10000)
    state: Literal["active", "paused"]


def summary(path: StudentLearningPath) -> dict[str, Any]:
    return {
        "id": str(path.id),
        "title": path.title,
        "language": path.language,
        "project_id": str(path.project_id) if path.project_id else None,
        "goal_id": str(path.goal_id) if path.goal_id else None,
        "state": path.state,
        "version": path.version,
        "created_at": path.created_at.isoformat(),
        "assessment": "self_reported_recall",
        "policy": "source-recall-path/v1",
    }


class LearningPaths:
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

    async def owned(
        self,
        session: AsyncSession,
        user: uuid.UUID,
        path_id: uuid.UUID,
        project: uuid.UUID | None,
        *,
        lock: bool = False,
        deleted: bool = False,
    ) -> StudentLearningPath:
        await scope(session, user, project)
        query = select(StudentLearningPath).where(
            StudentLearningPath.id == path_id,
            StudentLearningPath.user_id == user,
            StudentLearningPath.project_id.is_not_distinct_from(project),
        )
        if not deleted:
            query = query.where(StudentLearningPath.state != "deleted")
        if lock:
            query = query.with_for_update()
        path = await session.scalar(query)
        if path is None:
            raise JobError("not_found", "Learning path not found.", 404)
        return path

    async def create(self, user: uuid.UUID, body: LearningPathIn) -> tuple[dict[str, Any], bool]:
        definition = body.model_dump(mode="json", exclude={"request_id"})
        digest = hashlib.sha256(
            json.dumps(
                definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
        async with self.transaction() as session:
            await scope(session, user, body.project_id)
            # One bounded quota/idempotency admission per owner, including SQLite.
            if (
                await session.scalar(select(User.id).where(User.id == user).with_for_update())
                is None
            ):
                raise JobError("not_found", "Owner not found.", 404)
            prior = await session.scalar(
                select(StudentLearningPath).where(
                    StudentLearningPath.user_id == user,
                    StudentLearningPath.request_id == body.request_id,
                )
            )
            if prior is not None:
                if prior.definition_hash != digest:
                    raise JobError(
                        "idempotency_conflict", "Request ID was used for a different learning path."
                    )
                if prior.state == "deleted":
                    raise JobError(
                        "path_deleted", "This request refers to a deleted learning path."
                    )
                return summary(prior), False
            if (
                body.goal_id is not None
                and await session.scalar(
                    select(PersonalGoal.id).where(
                        PersonalGoal.id == body.goal_id, PersonalGoal.user_id == user
                    )
                )
                is None
            ):
                raise JobError("not_found", "Goal not found.", 404)
            total, active = (
                await session.execute(
                    select(
                        func.count(StudentLearningPath.id),
                        func.count(case((StudentLearningPath.state != "deleted", 1))),
                    ).where(StudentLearningPath.user_id == user)
                )
            ).one()
            if total >= MAX_TOTAL_PATHS or active >= MAX_ACTIVE_PATHS:
                raise JobError("path_limit", "Learning path capacity reached.")
            card_ids = [c for step in body.steps for c in step.card_ids]
            # Same document->card lock order as the existing review/delete contract.
            documents = list(
                (
                    await session.scalars(
                        select(KnowledgeDocument)
                        .where(
                            KnowledgeDocument.id.in_(
                                select(StudyCard.document_id).where(StudyCard.id.in_(card_ids))
                            ),
                            KnowledgeDocument.user_id == user,
                            KnowledgeDocument.project_id.is_not_distinct_from(body.project_id),
                        )
                        .order_by(KnowledgeDocument.id)
                        .with_for_update()
                    )
                ).all()
            )
            indexed = {d.id: d for d in documents}
            cards = list(
                (
                    await session.scalars(
                        select(StudyCard)
                        .where(
                            StudyCard.id.in_(card_ids),
                            StudyCard.user_id == user,
                            StudyCard.project_id.is_not_distinct_from(body.project_id),
                        )
                        .order_by(StudyCard.id)
                        .with_for_update()
                    )
                ).all()
            )
            if len(cards) != len(card_ids) or any(c.document_id not in indexed for c in cards):
                raise JobError("not_found", "A path card is missing or outside this scope.", 404)
            if any(
                indexed[c.document_id].current_revision_id != c.revision_id
                or indexed[c.document_id].status not in ("indexed", "partial")
                for c in cards
            ):
                raise JobError(
                    "revision_conflict", "Use cards bound to current indexed source revisions."
                )
            by_id = {c.id: c for c in cards}
            steps = [
                {
                    "index": i,
                    "title": step.title,
                    "prerequisites": step.prerequisites,
                    "required_recalls": step.required_recalls,
                    "cards": [
                        {
                            "card_id": str(c.id),
                            "document_id": str(c.document_id),
                            "revision_id": str(c.revision_id),
                            "quote_start": c.quote_start,
                            "quote_end": c.quote_end,
                        }
                        for c in [by_id[cid] for cid in step.card_ids]
                    ],
                }
                for i, step in enumerate(body.steps)
            ]
            path = StudentLearningPath(
                user_id=user,
                project_id=body.project_id,
                goal_id=body.goal_id,
                request_id=body.request_id,
                definition_hash=digest,
                title=body.title,
                language=body.language,
                steps=steps,
            )
            session.add(path)
            await session.flush()
            audit(
                session,
                user,
                "student.path_create",
                "student_learning_path",
                path.id,
                {"definition_hash": digest, "steps": len(steps), "cards": len(card_ids)},
            )
            return summary(path), True

    async def evaluate(
        self,
        user: uuid.UUID,
        path_id: uuid.UUID,
        project: uuid.UUID | None = None,
        *,
        limit: int = 10,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 20:
            raise JobError("invalid_limit", "Choose one to20 recommendations.", 422)
        async with self.transaction(write=False) as session:
            path = await self.owned(session, user, path_id, project)
            required = {
                uuid.UUID(c["card_id"]): step["required_recalls"]
                for step in path.steps
                for c in step["cards"]
            }
            needed = case(required, value=StudyCard.id, else_=1)
            # One SQL snapshot for card versions AND their bounded recent events.
            # A concurrent review cannot mix a new event with an older card version.
            positives = (
                select(func.count(StudyReview.id))
                .where(
                    StudyReview.card_id == StudyCard.id,
                    StudyReview.expected_version >= StudyCard.version - needed,
                    StudyReview.expected_version < StudyCard.version,
                    StudyReview.rating.in_(("good", "easy")),
                )
                .correlate(StudyCard)
                .scalar_subquery()
            )
            rows = (
                await session.execute(
                    select(
                        StudyCard.id,
                        StudyCard.document_id,
                        StudyCard.revision_id,
                        StudyCard.quote_start,
                        StudyCard.quote_end,
                        StudyCard.version,
                        StudyCard.interval_days,
                        StudyCard.due_at,
                        positives.label("positive_reviews"),
                        KnowledgeDocument.current_revision_id,
                        KnowledgeDocument.status,
                    )
                    .join(KnowledgeDocument, KnowledgeDocument.id == StudyCard.document_id)
                    .where(
                        StudyCard.id.in_(required),
                        StudyCard.user_id == user,
                        StudyCard.project_id.is_not_distinct_from(project),
                        KnowledgeDocument.user_id == user,
                        KnowledgeDocument.project_id.is_not_distinct_from(project),
                    )
                )
            ).all()
            available = {str(row.id): row for row in rows}
            now = utcnow()
            met: set[int] = set()
            lessons, recommendations = [], []
            for step in path.steps:
                resolved = []
                for reference in step["cards"]:
                    row = available.get(reference["card_id"])
                    if (
                        row is not None
                        and str(row.document_id) == reference["document_id"]
                        and str(row.revision_id) == reference["revision_id"]
                        and row.quote_start == reference["quote_start"]
                        and row.quote_end == reference["quote_end"]
                        and row.current_revision_id == row.revision_id
                        and row.status in ("indexed", "partial")
                    ):
                        resolved.append(row)
                valid = len(resolved) == len(step["cards"])
                prerequisites_met = all(p in met for p in step["prerequisites"])
                checkpoints = [
                    r
                    for r in resolved
                    if r.version >= step["required_recalls"]
                    and r.positive_reviews == step["required_recalls"]
                    and r.interval_days > 0
                    and r.due_at > now
                ]
                done = valid and prerequisites_met and len(checkpoints) == len(resolved)
                if done:
                    met.add(step["index"])
                exhausted = any(r.version >= 10000 and r not in checkpoints for r in resolved)
                state = (
                    "source_unavailable"
                    if not valid
                    else "blocked_by_prerequisite"
                    if not prerequisites_met
                    else "review_budget_exhausted"
                    if exhausted
                    else "checkpoint_met"
                    if done
                    else "practice_needed"
                )
                lessons.append(
                    {
                        "index": step["index"],
                        "title": step["title"],
                        "state": state,
                        "prerequisites": step["prerequisites"],
                        "required_recalls": step["required_recalls"],
                        "source_cards": len(resolved),
                        "total_cards": len(step["cards"]),
                        "checkpoint_cards": len(checkpoints),
                        "cards": step["cards"],
                    }
                )
                if (
                    valid
                    and prerequisites_met
                    and not done
                    and not exhausted
                    and path.state == "active"
                ):
                    for row in sorted(resolved, key=lambda r: (r.interval_days, r.due_at, r.id)):
                        if row in checkpoints:
                            continue
                        recommendations.append(
                            {
                                "step": step["index"],
                                "action": "review_card" if row.due_at <= now else "read_source",
                                "card_id": str(row.id),
                                "document_id": str(row.document_id),
                                "revision_id": str(row.revision_id),
                                "quote_start": row.quote_start,
                                "quote_end": row.quote_end,
                                "offset_unit": "unicode_codepoints",
                                "expected_version": row.version,
                                "due_at": row.due_at.isoformat(),
                                "reason": "due_recall"
                                if row.due_at <= now
                                else "review_not_due_yet",
                            }
                        )
            return {
                **summary(path),
                "evaluated_at": now.isoformat(),
                "steps": lessons,
                "checkpoint_steps": len(met),
                "total_steps": len(path.steps),
                "recommendations": recommendations[:limit],
                "action_authority": "none",
                "evidence": "recent_explicit_review_events_on_current_source_revisions",
                "mastery_claim": False,
            }

    async def set_state(
        self, user: uuid.UUID, path_id: uuid.UUID, body: PathStateIn
    ) -> dict[str, Any]:
        async with self.transaction() as session:
            path = await self.owned(session, user, path_id, body.project_id, lock=True)
            if path.version != body.expected_version:
                raise JobError("path_conflict", "The path changed. Reload it.")
            if path.version >= 10000:
                raise JobError("version_limit", "Learning path change budget exhausted.")
            path.state, path.version = body.state, path.version + 1
            audit(
                session,
                user,
                "student.path_state",
                "student_learning_path",
                path.id,
                {"state": path.state, "version": path.version},
            )
            return summary(path)

    async def delete(
        self, user: uuid.UUID, path_id: uuid.UUID, project: uuid.UUID | None, *, confirm: bool
    ) -> None:
        async with self.transaction() as session:
            path = await self.owned(session, user, path_id, project, lock=True, deleted=True)
            if not confirm:
                raise JobError("confirmation_required", "Confirm deleting this learning path.")
            if path.state == "deleted":
                return
            path.state, path.steps, path.title, path.goal_id = "deleted", [], "", None
            # A bounded minimal tombstone prevents replay from recreating a deleted
            # definition. Source cards, review history and manual goals stay owned.
            audit(session, user, "student.path_delete", "student_learning_path", path.id, {})
