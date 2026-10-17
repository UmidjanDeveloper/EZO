"""Memory storage, retrieval and automatic capture."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.text import normalize
from ezo_api.db.base import utcnow
from ezo_api.db.models import Memory
from ezo_api.memory.extraction import MemoryCandidate, extract_safe_candidates
from ezo_api.memory.scoring import combined_score, relevance, stems

ALWAYS_INCLUDE_IMPORTANCE = 0.85
"""Profile memories at least this important are always given to the model."""
MAX_CANDIDATES_SCANNED = 500
DUPLICATE_SIMILARITY = 0.8


@dataclass(frozen=True, slots=True)
class RetrievedMemory:
    memory: Memory
    score: float


@dataclass(frozen=True, slots=True)
class CaptureResult:
    created: list[Memory]
    reinforced: list[Memory]
    skipped_sensitive: int


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _scope(self, user_id: uuid.UUID, project_id: uuid.UUID | None) -> list[Memory]:
        """Profile memories plus memories of the current project."""
        query = select(Memory).where(Memory.user_id == user_id)
        if project_id is None:
            query = query.where(Memory.memory_type == "profile")
        else:
            query = query.where(
                or_(Memory.memory_type == "profile", Memory.project_id == project_id)
            )
        query = query.order_by(Memory.importance.desc(), Memory.updated_at.desc()).limit(
            MAX_CANDIDATES_SCANNED
        )
        return list((await self.session.scalars(query)).all())

    async def retrieve(
        self,
        user_id: uuid.UUID,
        query: str,
        project_id: uuid.UUID | None = None,
        limit: int = 8,
    ) -> list[RetrievedMemory]:
        now = utcnow()
        query_stems = stems(query)
        scored: list[RetrievedMemory] = []
        for memory in await self._scope(user_id, project_id):
            rel = relevance(query_stems, memory.content)
            score = combined_score(rel, memory.importance, memory.updated_at, now)
            always = memory.memory_type == "profile" and memory.importance >= (
                ALWAYS_INCLUDE_IMPORTANCE
            )
            if rel > 0 or always:
                scored.append(RetrievedMemory(memory, round(score, 3)))
        scored.sort(key=lambda item: item.score, reverse=True)
        selected = scored[:limit]
        for item in selected:
            item.memory.last_accessed = now
        return selected

    async def _find_similar(
        self, user_id: uuid.UUID, project_id: uuid.UUID | None, content: str
    ) -> Memory | None:
        target = stems(content)
        normalized = normalize(content)
        for memory in await self._scope(user_id, project_id):
            if normalize(memory.content) == normalized:
                return memory
            existing = stems(memory.content)
            if target and existing:
                jaccard = len(target & existing) / len(target | existing)
                if jaccard >= DUPLICATE_SIMILARITY:
                    return memory
        return None

    async def capture_from_message(
        self,
        user_id: uuid.UUID,
        text: str,
        conversation_id: uuid.UUID,
        project_id: uuid.UUID | None,
    ) -> CaptureResult:
        """Store memorable, non-sensitive statements from a user message."""
        outcome = extract_safe_candidates(text)
        created: list[Memory] = []
        reinforced: list[Memory] = []
        for candidate in outcome.accepted:
            existing = await self._find_similar(user_id, project_id, candidate.content)
            if existing is not None:
                # Repetition is a signal: a repeated statement becomes more important.
                boosted = max(existing.importance, candidate.importance) + 0.05
                existing.importance = min(1.0, boosted)
                existing.confidence = max(existing.confidence, candidate.confidence)
                existing.updated_at = utcnow()
                reinforced.append(existing)
                continue
            created.append(
                self._new_from_candidate(user_id, candidate, conversation_id, project_id)
            )
        self.session.add_all(created)
        return CaptureResult(created, reinforced, outcome.skipped_sensitive)

    @staticmethod
    def _new_from_candidate(
        user_id: uuid.UUID,
        candidate: MemoryCandidate,
        conversation_id: uuid.UUID,
        project_id: uuid.UUID | None,
    ) -> Memory:
        # Inside a project, everything except personal facts belongs to the project.
        is_project = project_id is not None and candidate.category not in (
            "personal",
            "preference",
        )
        return Memory(
            user_id=user_id,
            project_id=project_id if is_project else None,
            memory_type="project" if is_project else "profile",
            category=candidate.category,
            content=candidate.content,
            source="auto",
            source_conversation_id=conversation_id,
            confidence=candidate.confidence,
            importance=candidate.importance,
            sensitive=False,
        )
