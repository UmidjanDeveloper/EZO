"""Fail closed: the legacy native launcher is not a production sandbox.

No application setting enables this exception. The context manager is solely for
controlled regression fixtures; production/API/worker code never enters it.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_FIXTURES: ContextVar[bool] = ContextVar("trusted_native_regression_fixtures", default=False)
ISOLATION_MESSAGE = (
    "Document processing requires a verified isolated executor with whole-workload "
    "memory, termination and cancellation controls. This executor is unavailable."
)


class IsolationUnavailable(RuntimeError):
    """Safe, fixed error; no document contents or host paths."""


def native_fixtures_allowed() -> bool:
    return _FIXTURES.get()


def require_isolation() -> None:
    if not native_fixtures_allowed():
        raise IsolationUnavailable(ISOLATION_MESSAGE)


@contextmanager
def trusted_native_regression_fixtures() -> Iterator[None]:
    """Only tests with repository-owned fixtures may enter this context."""
    token = _FIXTURES.set(True)
    try:
        yield
    finally:
        _FIXTURES.reset(token)
