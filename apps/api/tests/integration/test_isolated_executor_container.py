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


def test_second_controller_cannot_exceed_daemon_workload_budget() -> None:
    assert IMAGE and PROBE
    before = names()
    cancelled = threading.Event()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(IsolatedExecutor(PROBE).extract, b"stall", "pdf", cancelled=cancelled)
        try:
            wait_new(before)
            with pytest.raises(ExecutorError, match="executor_busy"):
                IsolatedExecutor(IMAGE).extract(book(), "epub")
        finally:
            cancelled.set()
            with pytest.raises(ExecutorError):
                future.result(timeout=35)
    assert names() == before


def test_atomic_creation_loser_does_not_remove_winning_workload() -> None:
    assert PROBE
    before = names()
    barrier = threading.Barrier(2)
    cancelled = threading.Event()

    class SimultaneousControllers(IsolatedExecutor):
        def _recover_slot(self) -> None:
            super()._recover_slot()
            barrier.wait(timeout=10)

    with concurrent.futures.ThreadPoolExecutor() as pool:
        futures = [
            pool.submit(
                SimultaneousControllers(PROBE).extract, b"stall", "pdf", cancelled=cancelled
            )
            for _ in range(2)
        ]
        try:
            done, pending = concurrent.futures.wait(
                futures, timeout=20, return_when=concurrent.futures.FIRST_COMPLETED
            )
            assert len(done) == len(pending) == 1
            with pytest.raises(ExecutorError, match="executor_busy"):
                done.pop().result()
            name = wait_new(before)
            assert name in names()  # losing creator's finally did not kill the winner
        finally:
            cancelled.set()
            for future in futures:
                with pytest.raises(ExecutorError):
                    future.result(timeout=35)
    assert names() == before


def test_stopped_crash_residue_is_recovered_without_force() -> None:
    assert IMAGE
    from ezo_api.documents.executor.controller import SLOT_NAME

    before = names()
    identity = subprocess.check_output(
        [
            DOCKER,
            "create",
            "--name",
            SLOT_NAME,
            "--label=ezo.executor=isolated-v1",
            "--label=ezo.executor.slot=single-v1",
            IMAGE,
        ],
        text=True,
    ).strip()
    try:
        # Repository-owned command only; this image's parser entrypoint is not run.
        subprocess.run([DOCKER, "start", identity], check=True, capture_output=True)
        subprocess.check_output([DOCKER, "wait", identity], timeout=35)
        assert IsolatedExecutor(IMAGE).extract(book(), "epub").text == "Salom"
    finally:
        subprocess.run([DOCKER, "rm", "-f", identity], check=False, capture_output=True)
    assert names() == before


def test_fresh_created_reservation_is_not_stolen() -> None:
    assert IMAGE
    from ezo_api.documents.executor.controller import SLOT_NAME

    identity = subprocess.check_output(
        [
            DOCKER,
            "create",
            "--name",
            SLOT_NAME,
            "--label=ezo.executor=isolated-v1",
            "--label=ezo.executor.slot=single-v1",
            IMAGE,
        ],
        text=True,
    ).strip()
    try:
        with pytest.raises(ExecutorError, match="executor_busy"):
            IsolatedExecutor(IMAGE).extract(book(), "epub")
        assert (
            subprocess.check_output(
                [DOCKER, "inspect", "--format", "{{.Id}}", SLOT_NAME], text=True
            ).strip()
            == identity
        )
    finally:
        subprocess.run([DOCKER, "rm", identity], check=True, capture_output=True)


def test_delayed_old_controller_cannot_start_or_remove_replacement() -> None:
    assert IMAGE
    from ezo_api.documents.executor.controller import SLOT_NAME

    replacement = ""

    class ReplaceBeforeAttach(IsolatedExecutor):
        def _verify(self, identity: str) -> None:
            nonlocal replacement
            super()._verify(identity)
            self._docker("rm", identity)
            replacement = (
                self._docker(
                    "create",
                    "--name",
                    SLOT_NAME,
                    "--label=ezo.executor=isolated-v1",
                    "--label=ezo.executor.slot=single-v1",
                    "--label=ezo.executor.request=replacement-fixture",
                    self.image,
                )
                .decode()
                .strip()
            )

    try:
        with pytest.raises(ExecutorError):
            ReplaceBeforeAttach(IMAGE).extract(book(), "epub")
        assert (
            subprocess.check_output(
                [DOCKER, "inspect", "--format", "{{.State.Status}}", replacement], text=True
            ).strip()
            == "created"
        )
    finally:
        if replacement:
            subprocess.run([DOCKER, "rm", replacement], check=True, capture_output=True)


def test_foreign_reserved_name_is_never_deleted() -> None:
    assert IMAGE
    from ezo_api.documents.executor.controller import SLOT_NAME

    identity = subprocess.check_output(
        [DOCKER, "create", "--name", SLOT_NAME, IMAGE], text=True
    ).strip()
    try:
        with pytest.raises(ExecutorError, match="executor_slot_conflict"):
            IsolatedExecutor(IMAGE).extract(book(), "epub")
        assert (
            subprocess.check_output(
                [DOCKER, "inspect", "--format", "{{.Id}}", SLOT_NAME], text=True
            ).strip()
            == identity
        )
    finally:
        subprocess.run([DOCKER, "rm", identity], check=True, capture_output=True)


def test_abandoned_created_reservation_recovers_with_simulated_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert IMAGE
    from ezo_api.documents.executor import controller

    identity = subprocess.check_output(
        [
            DOCKER,
            "create",
            "--name",
            controller.SLOT_NAME,
            "--label=ezo.executor=isolated-v1",
            "--label=ezo.executor.slot=single-v1",
            IMAGE,
        ],
        text=True,
    ).strip()
    try:
        # Simulate the 120-second admission grace expiring; do not claim a real
        # two-minute wall-clock test. The actual Docker created-state path runs.
        monkeypatch.setattr(controller, "CREATED_GRACE_SECONDS", 0)
        assert IsolatedExecutor(IMAGE).extract(book(), "epub").text == "Salom"
    finally:
        subprocess.run([DOCKER, "rm", identity], check=False, capture_output=True)
