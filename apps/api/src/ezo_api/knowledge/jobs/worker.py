"""One bounded stored-text consumer. No parser, provider or native command executes.

Run separately: python -m ezo_api.knowledge.jobs.worker
SQLite supports one such worker only. PostgreSQL supports competing consumers.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import signal
from collections.abc import Sequence
from contextlib import suppress

from ezo_api.db.session import Database
from ezo_api.knowledge.jobs.service import MAX_SPANS, DocumentJobs, JobError
from ezo_api.schemas.document_jobs import CitationSpan
from ezo_api.settings import Settings

logger = logging.getLogger(__name__)


def paragraph_spans(value: str) -> list[CitationSpan]:
    """Exact global paragraph offsets; coalesce the tail at the publication cap."""
    spans: list[CitationSpan] = []
    start = 0
    while start < len(value):
        end = value.find("\n\n", start)
        if end < 0 or len(spans) == MAX_SPANS - 1:
            end = len(value)
        if end > start:
            spans.append(CitationSpan(start=start, end=end))
        start = end + 2
    return spans


class StoredTextWorker:
    def __init__(
        self,
        jobs: DocumentJobs,
        worker_id: str,
        *,
        poll_seconds: float = 1,
        deadline_seconds: float = 20,
    ) -> None:
        # Deadline stays strictly inside the minimum accepted lease duration.
        if not 0.05 <= poll_seconds <= 30 or not 0 < deadline_seconds < jobs.lease_seconds:
            raise ValueError(
                "Worker requires bounded polling and a deadline shorter than its lease"
            )
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", worker_id):
            raise ValueError("Invalid worker identifier")
        self.jobs, self.worker_id = jobs, worker_id
        self.poll_seconds, self.deadline_seconds = poll_seconds, deadline_seconds

    async def process_one(self) -> bool:
        lease = None
        try:
            async with asyncio.timeout(self.deadline_seconds):
                lease = await self.jobs.claim(self.worker_id)
                if lease is None:
                    return False
                value = await self.jobs.read_input(lease)
                await self.jobs.publish(lease, value, paragraph_spans(value))
            return True
        except (TimeoutError, JobError) as exc:
            if lease is not None:
                # Fencing may already have revoked this lease; never revive it.
                with suppress(JobError, TimeoutError):
                    async with asyncio.timeout(5):
                        await self.jobs.fail(
                            lease, "transient" if isinstance(exc, TimeoutError) else "invalid_input"
                        )
            logger.warning("Stored-text job interrupted (%s)", type(exc).__name__)
            return lease is not None

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.process_one()
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)


async def serve(options: argparse.Namespace) -> None:
    settings = Settings()
    if settings.deployment_profile == "free-beta":
        raise RuntimeError("Autonomous workers are disabled in free beta.")
    db = Database(settings.database_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        worker = StoredTextWorker(DocumentJobs(db), options.worker_id)
        await worker.run(stop)
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        await db.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", required=True, help="1..80 ASCII letters/digits/_.-")
    asyncio.run(serve(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
