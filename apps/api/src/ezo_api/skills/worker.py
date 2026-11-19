"""`python -m ezo_api.skills.worker --image sha256:…` — runs queued skill runs.

The only EZO process that talks to Docker for skills (runs as the `skill-worker` service of
the `skills` Compose profile, like the document worker). It re-checks that the run's code
hash is still the owner-approved one before running it.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
from typing import Any

from sqlalchemy import select, update

from ezo_api.db.base import utcnow
from ezo_api.db.models import Skill, SkillRun
from ezo_api.db.session import Database
from ezo_api.settings import Settings
from ezo_api.skills.sandbox import SandboxError, SkillSandbox

logger = logging.getLogger("ezo.skills.worker")


async def run_once(db: Database, sandbox: Any, worker_id: str) -> bool:
    """Claim and run one queued run. Returns False when nothing was queued."""
    async with db.sessionmaker() as session:
        run = await session.scalar(
            select(SkillRun)
            .where(SkillRun.status == "queued")
            .order_by(SkillRun.created_at)
            .limit(1)
        )
        if run is None:
            return False
        claimed = await session.execute(
            update(SkillRun)
            .where(SkillRun.id == run.id, SkillRun.status == "queued")
            .values(status="running", worker_id=worker_id, started_at=utcnow())
        )
        await session.commit()
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            return True  # another worker took it
        run = await session.get(SkillRun, run.id, populate_existing=True)
        assert run is not None
        skill = await session.get(Skill, run.skill_id)
        if (
            skill is None
            or skill.approved_sha256 != run.code_sha256
            or skill.code_sha256 != run.code_sha256
        ):
            run.status, run.error, run.finished_at = (
                "failed",
                "The approved code changed; nothing was run.",
                utcnow(),
            )
            await session.commit()
            return True
        code, data = skill.code, run.input
    try:
        result = await asyncio.to_thread(sandbox.run, code, data)
        values: dict[str, Any] = {
            "status": "completed" if result.ok else "failed",
            "output": result.result if result.ok else None,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }
    except SandboxError as exc:
        values = {"status": "failed", "error": exc.message}
    async with db.sessionmaker() as session:
        await session.execute(
            update(SkillRun).where(SkillRun.id == run.id).values(finished_at=utcnow(), **values)
        )
        await session.commit()
    logger.info("skill run %s %s", run.id, values["status"])
    return True


async def serve(image: str, worker_id: str, poll_seconds: float = 0.5) -> None:
    settings = Settings()
    db = Database(settings.database_url)
    sandbox = SkillSandbox(image)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    logger.info("EZO skill worker %s ready (image %s)", worker_id, image)
    try:
        while not stop.is_set():
            try:
                busy = await run_once(db, sandbox, worker_id)
            except Exception:
                logger.exception("skill worker step failed")
                busy = False
            if not busy:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ezo_api.skills.worker")
    parser.add_argument("--image", required=True, help="immutable image ID (sha256:…)")
    parser.add_argument("--worker-id", default="local-skills-1")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(serve(args.image, args.worker_id))


if __name__ == "__main__":
    main()
