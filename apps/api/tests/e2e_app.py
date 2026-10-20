"""ASGI harness for controlled browser fixtures only; never the application entrypoint.

Legacy browser journeys use repository-owned images/templates and localhost fixture
pages. Production fail-closed behavior is tested separately without this exception.
"""

from starlette.types import Receive, Scope, Send

from ezo_api.documents.isolation import trusted_native_regression_fixtures
from ezo_api.main import create_app


def create_fixture_app():
    with trusted_native_regression_fixtures():
        application = create_app()

    async def fixtures(scope: Scope, receive: Receive, send: Send) -> None:
        with trusted_native_regression_fixtures():
            await application(scope, receive, send)

    return fixtures
