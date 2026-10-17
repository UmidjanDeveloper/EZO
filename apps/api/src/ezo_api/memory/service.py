"""Memory storage, retrieval and automatic capture."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.core.text import normalize
from ezo_api.db.base import utcnow
from ezo_api.db.models import Memory
from ezo_api.knowledge.embeddings.service import EmbeddingError, EmbeddingService
from ezo_api.knowledge.vectorstores import VectorFilter, VectorRecord, VectorStoreResolver
from ezo_api.memory.extraction import MemoryCandidate, extract_safe_candidates
from ezo_api.memory.scoring import combined_score, hybrid_score, relevance, stems

logger = logging.getLogger(__name__)

ALWAYS_INCLUDE_IMPORTANCE = 0.85
"""Profile memories at least this important are always given to the model."""
MAX_CANDIDATES_SCANNED = 500
DUPLICATE_SIMILARITY = 0.8
SEMANTIC_MIN = 0.40
"""Below this cosine similarity a memory is not considered related (avoids over-retrieval)."""
DEFAULT_LIMIT = 6


@dataclass(frozen=True, slots=True)
class MemoryIndex:
    """Embeddings for semantic memory retrieval (optional)."""

    embeddings: EmbeddingService
    vectors: VectorStoreResolver


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
    def __init__(self, session: AsyncSession, index: MemoryIndex | None = None) -> None:
        self.session = session
        self.index = index if index and index.embeddings.available else None

    async def _semantic_scores(
        self, user_id: uuid.UUID, query: str, project_id: uuid.UUID | None
    ) -> dict[uuid.UUID, float]:
        if self.index is None or not query.strip():
            return {}
        try:
            vector = await self.index.embeddings.embed_query(query)
            store = await self.index.vectors.get(self.session)
            hits = await store.search(
                self.session,
                vector,
                VectorFilter(
                    user_id=user_id,
                    owner_type="memory",
                    model=self.index.embeddings.model_key or "",
                    project_scope=project_id,
                ),
                limit=20,
            )
        except EmbeddingError as exc:
            logger.info("Semantic memory search unavailable: %s", exc.message)
            return {}
        return {hit.owner_id: hit.score for hit in hits}

    async def index_memories(self, memories: Sequence[Memory]) -> int:
        """Embed memories for semantic retrieval. Best effort: failures are logged."""
        if self.index is None or not memories:
            return 0
        try:
            vectors = await self.index.embeddings.embed_documents([m.content for m in memories])
            store = await self.index.vectors.get(self.session)
            await store.upsert(
                self.session,
                [
                    VectorRecord(
                        owner_type="memory",
                        owner_id=memory.id,
                        user_id=memory.user_id,
                        model=self.index.embeddings.model_key or "",
                        vector=vector,
                        project_id=memory.project_id,
                    )
                    for memory, vector in zip(memories, vectors, strict=True)
                ],
            )
        except EmbeddingError as exc:
            logger.warning("Could not embed memories: %s", exc.message)
            return 0
        return len(memories)

    async def forget_vectors(self, memory_ids: Sequence[uuid.UUID]) -> None:
        if self.index is None:
            return
        store = await self.index.vectors.get(self.session)
        await store.delete_owners(self.session, "memory", memory_ids)

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
        limit: int = DEFAULT_LIMIT,
    ) -> list[RetrievedMemory]:
        """Relevant memories: semantic similarity + importance + recency + project
        relevance when embeddings are available, lexical overlap otherwise."""
        now = utcnow()
        query_stems = stems(query)
        semantic = await self._semantic_scores(user_id, query, project_id)
        scored: list[RetrievedMemory] = []
        for memory in await self._scope(user_id, project_id):
            lexical = relevance(query_stems, memory.content)
            similarity = semantic.get(memory.id)
            always = memory.memory_type == "profile" and memory.importance >= (
                ALWAYS_INCLUDE_IMPORTANCE
            )
            if similarity is not None:
                score = hybrid_score(
                    similarity,
                    lexical,
                    memory.importance,
                    memory.updated_at,
                    now,
                    project_match=project_id is not None and memory.project_id == project_id,
                )
                related = similarity >= SEMANTIC_MIN or lexical > 0
            else:
                score = combined_score(lexical, memory.importance, memory.updated_at, now)
                related = lexical > 0
            if related or always:
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
        if created:
            await self.session.flush()
            await self.index_memories(created)
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
