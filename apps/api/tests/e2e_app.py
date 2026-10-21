"""ASGI harness for controlled browser fixtures only; never the application entrypoint.

Legacy browser journeys use repository-owned images/templates and localhost fixture
pages. Production fail-closed behavior is tested separately without this exception.
"""

import asyncio
from contextlib import asynccontextmanager

from starlette.types import Receive, Scope, Send

from ezo_api.documents.isolation import trusted_native_regression_fixtures
from ezo_api.knowledge.jobs.service import DocumentJobs
from ezo_api.knowledge.jobs.worker import StoredTextWorker
from ezo_api.main import create_app


def create_fixture_app():
    with trusted_native_regression_fixtures():
        application = create_app()

    original_lifespan = application.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original_lifespan(app):
            stop = asyncio.Event()
            task = asyncio.create_task(
                StoredTextWorker(
                    DocumentJobs(application.state.services.db),
                    "browser-text-fixture",
                    poll_seconds=0.05,
                ).run(stop)
            )
            try:
                yield
            finally:
                stop.set()
                await task

    application.router.lifespan_context = lifespan

    async def fixtures(scope: Scope, receive: Receive, send: Send) -> None:
        with trusted_native_regression_fixtures():
            await application(scope, receive, send)

    return fixtures
