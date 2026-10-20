"""Opt-in real Docker isolation tests. SQLite cannot establish these controls."""

# Fixed repository-owned Docker commands and fixtures, never document-supplied commands.
# ruff: noqa: S603

from __future__ import annotations

import concurrent.futures
import io
import os
import subprocess
import threading
import time
from pathlib import Path

import docx
import pytest
from reportlab.pdfgen.canvas import Canvas

from ezo_api.documents.executor.controller import DOCKER, IsolatedExecutor
from ezo_api.documents.executor.protocol import ExecutorError
from tests.unit.test_isolated_executor import book

IMAGE = os.environ.get("EZO_EXECUTOR_TEST_IMAGE")
PROBE = os.environ.get("EZO_EXECUTOR_PROBE_IMAGE")
pytestmark = pytest.mark.skipif(
    not IMAGE or not PROBE, reason="requires pinned isolated and hostile-fixture images"
)


def names() -> set[str]:
    return set(
        subprocess.check_output(
            [
                DOCKER,
                "ps",
                "-a",
                "--format",
                "{{.Names}}",
                "--filter",
                "label=ezo.executor=isolated-v1",
            ],
            text=True,
        ).split()
    )


def wait_new(previous: set[str]) -> str:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        new = names() - previous
        if new:
            name = new.pop()
            running = subprocess.check_output(
                [DOCKER, "inspect", "--format", "{{.State.Running}}", name], text=True
            )
            if running.strip() == "true":
                return name
        time.sleep(0.1)
    raise AssertionError("workload did not start")


@pytest.mark.parametrize("format", ["pdf", "docx", "epub"])
def test_real_documents_exact_citations(format: str) -> None:
    assert IMAGE
    if format == "epub":
        data = book("<html><body>Oʻzbek 🙂 Русский</body></html>".encode())
    elif format == "docx":
        document = docx.Document()
        document.add_paragraph("Oʻzbek 🙂 Русский")
        output = io.BytesIO()
        document.save(output)
        data = output.getvalue()
    else:
        output = io.BytesIO()
        canvas = Canvas(output)
        canvas.drawString(20, 800, "EZO student reading")
        canvas.save()
        data = output.getvalue()
    result = IsolatedExecutor(IMAGE).extract(data, format)  # type: ignore[arg-type]
    assert result.text
    assert result.sections[0].start == 0
    assert result.sections[-1].end == len(result.text)
    if format != "pdf":
        assert result.text == "Oʻzbek 🙂 Русский"
    else:
        assert result.sections[0].page == 1


def test_detached_descendants_do_not_hold_workload_open() -> None:
    assert PROBE
    before = names()
    start = time.monotonic()
    result = IsolatedExecutor(PROBE).extract(b"detached", "pdf")
    assert result.text == "detached"
    assert time.monotonic() - start < 20
    assert names() == before


def test_aggregate_memory_limit() -> None:
    assert PROBE
    before = names()
    result = IsolatedExecutor(PROBE).extract(b"memory", "pdf")
    assert result.text == "aggregate_oom_enforced"
    assert names() == before


def test_physical_cancellation_removes_namespace() -> None:
    assert PROBE
    before = names()
    cancelled = threading.Event()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(IsolatedExecutor(PROBE).extract, b"stall", "pdf", cancelled=cancelled)
        name = wait_new(before)
        cancelled.set()
        with pytest.raises(ExecutorError, match="cancelled"):
            future.result(timeout=20)
    assert name not in names()


def test_controller_crash_cannot_disable_root_watchdog(tmp_path: Path) -> None:
    assert PROBE
    before = names()
    script = tmp_path / "controller.py"
    script.write_text(
        "from ezo_api.documents.executor.controller import IsolatedExecutor\n"
        + f'IsolatedExecutor({PROBE!r}).extract(b"watchdog", "pdf")\n'
    )
    process = subprocess.Popen([os.sys.executable, str(script)])
    name = ""
    try:
        name = wait_new(before)
        process.kill()
        process.wait(timeout=5)
        # Workload deadline is independent of this controller and the parser cannot
        # SIGSTOP the root timeout process. Docker wait observes namespace exit.
        started = time.monotonic()
        code = subprocess.check_output([DOCKER, "wait", name], timeout=35, text=True)
        assert int(code) == 137
        assert time.monotonic() - started >= 20
        running = subprocess.check_output(
            [DOCKER, "inspect", "--format", "{{.State.Running}}", name], text=True
        )
        assert running.strip() == "false"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if name:
            subprocess.run([DOCKER, "rm", "-f", name], check=True, capture_output=True)
    assert names() == before


def test_output_flood_is_bounded_and_removed() -> None:
    assert PROBE
    before = names()
    with pytest.raises(ExecutorError, match="output_limit"):
        IsolatedExecutor(PROBE).extract(b"flood", "pdf")
    assert names() == before


def test_malformed_input_returns_no_private_stderr() -> None:
    assert IMAGE
    before = names()
    with pytest.raises(ExecutorError) as caught:
        IsolatedExecutor(IMAGE).extract(b"private_document_secret", "pdf")
    assert str(caught.value) == "Isolated document processing failed: processing_failed"
    assert names() == before


def test_cancellation_during_cleanup_does_not_acknowledge_result() -> None:
    assert IMAGE
    cancelled = threading.Event()
    before = names()

    class CancelOnCleanup(IsolatedExecutor):
        @staticmethod
        def _docker(*args: str) -> bytes:
            result = IsolatedExecutor._docker(*args)
            if args[0] == "rm":
                cancelled.set()
            return result

    with pytest.raises(ExecutorError, match="cancelled"):
        CancelOnCleanup(IMAGE).extract(book(), "epub", cancelled=cancelled)
    assert names() == before
