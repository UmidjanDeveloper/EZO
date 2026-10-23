"""Dedicated operator host only; NEVER run in the API or mount its Docker socket there.

python -m ezo_api.student.worker --worker-id student-1 --image sha256:... \
    --ack-dedicated-executor-host

PostgreSQL required. The operator must isolate this trusted controller/DB identity
from parser containers and other Docker clients. No production activation is implied.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import threading
from contextlib import suppress
from typing import cast

from ezo_api.db.session import Database
from ezo_api.documents.executor.controller import IsolatedExecutor
from ezo_api.documents.executor.protocol import ExecutorError
from ezo_api.knowledge.jobs.service import FailCode, JobError
from ezo_api.settings import Settings
from ezo_api.student.ingestion import StudentIngestion

FATAL_EXECUTOR_ERRORS = frozenset(
    {
        "cleanup_failed",
        "isolation_unavailable",
        "invalid_container_identity",
        "executor_slot_conflict",
    }
)


class StudentWorker:
    def __init__(self, jobs: StudentIngestion, executor: IsolatedExecutor, worker_id: str):
        if jobs.lease_seconds < 120:
            raise ValueError("Native processing requires a lease of at least 120 seconds")
        self.jobs, self.executor, self.worker_id = jobs, executor, worker_id

    async def process_one(self, stop: asyncio.Event | None = None) -> bool:
        lease = await self.jobs.claim(self.worker_id)
        if lease is None:
            return False
        cancelled = threading.Event()
        task = None
        try:
            async with asyncio.timeout(90):
                data, format, languages = await self.jobs.raw_input(lease)
                task = asyncio.create_task(
                    asyncio.to_thread(
                        self.executor.extract,
                        data,
                        format,
                        ocr_languages=languages,
                        cancelled=cancelled,
                    )
                )
                while not task.done():
                    if stop is not None and stop.is_set():
                        raise JobError("shutdown", "Worker is stopping.")
                    # Check, do not extend: the whole-job deadline stays inside its lease.
                    async with self.jobs._transaction() as session:
                        await self.jobs._leased(session, lease)
                    await asyncio.wait({task}, timeout=0.25)
                result = task.result()
                await self.jobs.publish_extraction(lease, result)
        except (JobError, ExecutorError, TimeoutError) as exc:
            cancelled.set()
            fatal = (
                exc
                if isinstance(exc, ExecutorError) and exc.code in FATAL_EXECUTOR_ERRORS
                else None
            )
            if task is not None:
                # Join, never detach the controller, even after cancellation/lease loss.
                try:
                    await asyncio.shield(task)
                except ExecutorError as thread_error:
                    if thread_error.code in FATAL_EXECUTOR_ERRORS:
                        fatal = thread_error
            if fatal is not None:
                if fatal.code != "cleanup_failed":
                    # These fixed errors occur before Docker start/input consumption.
                    # Revoke/refund the unadmitted claim, then stop the whole worker.
                    with suppress(JobError):
                        await self.jobs.defer_admission(lease)
                # Unknown cleanup outcome retains its fenced running lease. No new
                # claim is allowed; independent watchdog + operator recovery apply.
                raise fatal from None
            transient = isinstance(exc, TimeoutError) or getattr(exc, "code", "") in (
                "executor_busy",
                "executor_unavailable",
                "shutdown",
            )
            with suppress(JobError):
                if isinstance(exc, ExecutorError) and exc.code == "executor_busy":
                    await self.jobs.defer_admission(lease)
                elif isinstance(exc, JobError) and exc.code in ("ocr_required", "ocr_incomplete"):
                    await self.jobs.fail(lease, cast(FailCode, exc.code))
                else:
                    await self.jobs.fail(lease, "transient" if transient else "invalid_input")
        except BaseException:
            cancelled.set()
            if task is not None:
                with suppress(ExecutorError):
                    await asyncio.shield(task)
            raise
        return True

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.process_one(stop)
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1)


async def serve(args: argparse.Namespace) -> None:
    settings = Settings()
    if settings.deployment_profile == "free-beta":
        raise RuntimeError("Autonomous workers are disabled in free beta.")
    db = Database(settings.database_url)
    if db.engine.dialect.name != "postgresql":
        await db.dispose()
        raise ValueError("Dedicated Student native workers require PostgreSQL")
    executor = IsolatedExecutor(args.image)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await StudentWorker(StudentIngestion(db), executor, args.worker_id).run(stop)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--image", required=True, help="Trusted immutable local executor image ID")
    parser.add_argument("--ack-dedicated-executor-host", action="store_true", required=True)
    try:
        asyncio.run(serve(parser.parse_args()))
    except Exception as exc:
        # SQL/SDK exception repr may include private bytes or database parameters.
        logging.getLogger(__name__).error("Student worker stopped (%s)", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
