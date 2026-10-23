"""Run bounded governed refresh and explicitly consented schedules.

python -m ezo_api.learning.refresh_cli
No native processing, shell, generated code, daemon provisioning or paid calls
are enabled by this command. Configured embedding providers may incur charges.
"""

import asyncio
import contextlib
import logging
import os
import signal

from ezo_api.deployment import (
    check_database,
    check_environment,
    configure_production_logging,
    validate_production,
)
from ezo_api.learning.refresh import RefreshQueue
from ezo_api.learning.refresh_worker import RefreshWorker
from ezo_api.services import build_services
from ezo_api.settings import Settings

logger = logging.getLogger(__name__)


async def serve() -> None:
    settings = Settings()
    if settings.deployment_profile == "free-beta" or not settings.learning_enabled:
        raise RuntimeError("Governed refresh worker is disabled in this profile.")
    check_environment(settings, os.environ)
    validate_production(settings)
    configure_production_logging(settings)
    await asyncio.to_thread(check_database, settings)
    services = build_services(settings)
    assert services.learning is not None
    queue = RefreshQueue(services.db)
    worker = RefreshWorker(queue, services.learning.service)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await poll(queue, worker, stop)
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        await services.learning.shutdown()
        await services.ingestion.shutdown()
        await services.storage.aclose()
        await services.db.dispose()


async def poll(
    queue: RefreshQueue, worker: RefreshWorker, stop: asyncio.Event, *, poll_seconds: float = 10
) -> None:
    if not 0.05 <= poll_seconds <= 30:
        raise ValueError("Invalid polling interval")

    async def cycle() -> None:
        await queue.schedule_due()
        await worker.process_one()
        await worker.cleanup()

    while not stop.is_set():
        task = asyncio.create_task(cycle(), name="governed-refresh-cycle")
        stopped = asyncio.create_task(stop.wait(), name="governed-refresh-stop")
        try:
            done, _ = await asyncio.wait((task, stopped), return_when=asyncio.FIRST_COMPLETED)
            if stopped in done and not task.done():
                task.cancel()
            await task
        except asyncio.CancelledError:
            if stop.is_set():
                break
            raise
        except Exception:
            logger.exception("Refresh poll failed; no run marked successful")
        finally:
            for owned in (task, stopped):
                if not owned.done():
                    owned.cancel()
            await asyncio.gather(task, stopped, return_exceptions=True)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)


if __name__ == "__main__":
    asyncio.run(serve())
