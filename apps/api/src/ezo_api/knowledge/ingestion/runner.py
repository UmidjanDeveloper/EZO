"""Runs ingestion in the background (or inline for tests and small setups).

Background work is real and observable: each document's status is stored in
the database (queued → processing → indexed/partial/needs_ocr/failed), and
documents left unfinished by a restart are picked up again at startup.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ezo_api.db.models import KnowledgeDocument
from ezo_api.knowledge.ingestion.service import KnowledgeService

logger = logging.getLogger(__name__)


class IngestionRunner:
    def __init__(
        self,
        service: KnowledgeService,
        sessionmaker: async_sessionmaker,  # type: ignore[type-arg]
        mode: str = "background",
        concurrency: int = 2,
    ) -> None:
        self.service = service
        self.sessionmaker = sessionmaker
        self.mode = mode
        self._semaphore = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task[None]] = set()

    async def _run(self, document_id: uuid.UUID) -> None:
        async with self._semaphore, self.sessionmaker() as session:
            try:
                await self.service.ingest(session, document_id)
            except LookupError:
                logger.info("Document %s was deleted before ingestion", document_id)

    async def submit(self, document_id: uuid.UUID) -> None:
        if self.mode == "inline":
            await self._run(document_id)
            return
        task = asyncio.create_task(self._run(document_id), name=f"ingest-{document_id}")
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Ingestion task failed", exc_info=task.exception())

    async def resume_unfinished(self) -> int:
        """Re-queue documents interrupted by a restart."""
        async with self.sessionmaker() as session:
            ids = (
                await session.scalars(
                    select(KnowledgeDocument.id).where(
                        KnowledgeDocument.status.in_(("queued", "processing")),
                        KnowledgeDocument.meta["student"].as_boolean().is_not(True),
                    )
                )
            ).all()
        for document_id in ids:
            await self.submit(document_id)
        return len(ids)

    async def wait_idle(self) -> None:
        """Wait for running background ingestion (used at shutdown and in tests)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
