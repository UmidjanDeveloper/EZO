"""Fail closed: the legacy native launcher is not a production sandbox.

No application setting enables this exception. Native OCR/Office commands may run
only in one of two contexts:

- `trusted_native_regression_fixtures()`: controlled repository fixtures in tests;
- `verified_executor_workload()`: the isolated executor child process, entered
  only after it has verified its own container boundary (UID, capabilities,
  cgroup limits, loopback-only network, read-only root). Entering it anywhere
  else (API, worker, controller) fails because those checks do not hold there.

Production/API/worker code never enters either context.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_FIXTURES: ContextVar[bool] = ContextVar("trusted_native_regression_fixtures", default=False)
_EXECUTOR: ContextVar[bool] = ContextVar("verified_executor_workload", default=False)
ISOLATION_MESSAGE = (
    "Document processing requires a verified isolated executor with whole-workload "
    "memory, termination and cancellation controls. This executor is unavailable."
)


class IsolationUnavailable(RuntimeError):
    """Safe, fixed error; no document contents or host paths."""


def native_fixtures_allowed() -> bool:
    return _FIXTURES.get()


def native_execution_allowed() -> bool:
    """Fixed OCR/Office binaries may run: regression fixtures or a verified workload."""
    return _FIXTURES.get() or _EXECUTOR.get()


def require_isolation() -> None:
    if not native_execution_allowed():
        raise IsolationUnavailable(ISOLATION_MESSAGE)


@contextmanager
def trusted_native_regression_fixtures() -> Iterator[None]:
    """Only tests with repository-owned fixtures may enter this context."""
    token = _FIXTURES.set(True)
    try:
        yield
    finally:
        _FIXTURES.reset(token)


@contextmanager
def verified_executor_workload() -> Iterator[None]:
    """Only the executor child, after its own boundary checks pass, may enter this.

    The boundary check runs here (not in the caller) so no caller can skip it.
    """
    from ezo_api.documents.executor.boundary import verify_boundary

    verify_boundary()
    token = _EXECUTOR.set(True)
    try:
        yield
    finally:
        _EXECUTOR.reset(token)
