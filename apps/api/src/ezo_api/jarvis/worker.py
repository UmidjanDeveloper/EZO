"""JARVIS document worker — dedicated operator host only (like the Student worker).

    python -m ezo_api.jarvis.worker --worker-id jarvis-1 --image sha256:... \
        --ack-dedicated-executor-host

It advances JARVIS tasks whose next step needs untrusted-document processing
(reading PDF/DOCX/XLSX/PPTX or converting Office files to PDF). Those operations run
ONLY inside the per-document isolated executor container; the API process never
parses them. PostgreSQL required. Never mount the Docker socket into the API.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from contextlib import suppress
from typing import Literal, cast

from sqlalchemy import select

from ezo_api.db.models import JarvisTask
from ezo_api.db.session import Database
from ezo_api.documents.executor.controller import IsolatedExecutor
from ezo_api.documents.executor.protocol import OCR_LANGUAGES
from ezo_api.jarvis.service import Converter, Extractor, JarvisService, Workers
from ezo_api.jarvis.telegram import TelegramClient
from ezo_api.settings import Settings

logger = logging.getLogger(__name__)


def executor_workers(executor: IsolatedExecutor) -> tuple[Extractor, Converter]:
    async def convert(data: bytes, extension: str) -> bytes:
        kind = cast(Literal["docx", "xlsx", "pptx"], extension)
        pdf, _ = await asyncio.to_thread(executor.convert_to_pdf, data, kind)
        return pdf

    async def extract(data: bytes, extension: str) -> str:
        if extension in ("xlsx", "pptx"):
            # The executor reads PDF/DOCX/EPUB; sheets and decks are read via their PDF.
            data, extension = await convert(data, extension), "pdf"
        kind = cast(Literal["pdf", "docx"], extension)
        result = await asyncio.to_thread(executor.extract, data, kind, ocr_languages=OCR_LANGUAGES)
        if result.needs_ocr:
            raise ValueError("unreadable_scan")
        return result.text

    return extract, convert


async def run_once(db: Database, services: object, workers: Workers) -> int:
    """Advance every open task once; returns how many were looked at."""
    async with db.sessionmaker() as session:
        ids = (
            await session.scalars(
                select(JarvisTask.id).where(JarvisTask.state.in_(("queued", "running"))).limit(50)
            )
        ).all()
    for task_id in ids:
        async with db.sessionmaker() as session:
            task = await session.get(JarvisTask, task_id)
            if task is None:
                continue
            await JarvisService(session, services, workers).advance(task)
            await session.commit()
    return len(ids)


async def serve(args: argparse.Namespace) -> None:
    from ezo_api.services import build_services

    settings = Settings()
    db = Database(settings.database_url)
    if db.engine.dialect.name != "postgresql":
        await db.dispose()
        raise ValueError("The JARVIS document worker requires PostgreSQL")
    services = build_services(settings)
    extract, convert = executor_workers(IsolatedExecutor(args.image))
    token = settings.telegram_bot_token
    workers = Workers(
        extractor=extract,
        converter=convert,
        telegram=TelegramClient(token.get_secret_value())
        if token and token.get_secret_value()
        else None,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        while not stop.is_set():
            await run_once(db, services, workers)
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=2)
    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--image", required=True, help="Trusted immutable local executor image ID")
    parser.add_argument("--ack-dedicated-executor-host", action="store_true", required=True)
    try:
        asyncio.run(serve(parser.parse_args()))
    except Exception as exc:
        logger.error("JARVIS worker stopped (%s)", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
