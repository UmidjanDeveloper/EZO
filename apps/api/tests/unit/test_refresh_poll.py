"""The polling process owns all tasks, including shutdown during a queue/GC call."""

import asyncio
from types import SimpleNamespace

import pytest

from ezo_api.learning.refresh_cli import poll


@pytest.mark.parametrize("phase", ["schedule", "process", "cleanup"])
@pytest.mark.parametrize("shutdown", ["stop", "cancel"])
async def test_poll_cancels_and_joins_owned_cycle_in_every_phase(phase, shutdown):
    entered, cleaned, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def pause():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async def finished():
        return None

    queue = SimpleNamespace(schedule_due=pause if phase == "schedule" else finished)
    worker = SimpleNamespace(
        process_one=pause if phase == "process" else finished,
        cleanup=pause if phase == "cleanup" else finished,
    )
    task = asyncio.create_task(poll(queue, worker, stop, poll_seconds=0.05))
    await asyncio.wait_for(entered.wait(), 2)
    if shutdown == "stop":
        stop.set()
        await asyncio.wait_for(task, 2)
    else:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cleaned.is_set()
    assert not [
        t
        for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and t.get_name().startswith("governed-refresh-")
    ]
