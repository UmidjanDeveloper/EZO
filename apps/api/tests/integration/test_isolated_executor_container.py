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
from collections.abc import Callable
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


# --- OCR and Office conversion inside the same isolated workload ----------------------


def _scan(*pages: list[str]) -> bytes:
    from ezo_api.documents.pdf import engine
    from tests.ocr_fixtures import page_image, png

    return engine.images_to_pdf([png(page_image(lines)) for lines in pages]).data


@pytest.mark.parametrize(
    ("lines", "languages"),
    [
        ("UZ_LATIN", ("uzb",)),
        ("UZ_CYRILLIC", ("uzb_cyrl",)),
        ("RUSSIAN", ("rus",)),
        ("ENGLISH", ("eng",)),
        ("UZ_CYRILLIC", ("eng", "uzb", "uzb_cyrl", "rus")),  # default: all four
    ],
)
def test_scanned_pdf_ocr_in_the_isolated_workload(
    lines: str, languages: tuple[str, ...], record_property: Callable[[str, object], None]
) -> None:
    from tests import ocr_fixtures

    assert IMAGE
    expected = getattr(ocr_fixtures, lines)
    before = names()
    started = time.monotonic()
    result = IsolatedExecutor(IMAGE).extract(_scan(expected), "pdf", ocr_languages=languages)  # type: ignore[arg-type]
    elapsed = time.monotonic() - started
    record_property("ocr_seconds_1_page", round(elapsed, 2))
    assert result.ocr is not None and result.ocr.status == "completed", result.ocr
    assert not result.needs_ocr and result.ocr.pages == result.ocr.pages_read == 1
    assert ocr_fixtures.recall(expected, result.text) >= 0.9, result.text
    assert result.sections[0].page == 1 and result.sections[-1].end == len(result.text)
    assert result.ocr.mean_confidence is not None
    assert elapsed < 25
    assert names() == before


def test_multi_page_scan_keeps_page_numbers(record_property: Callable[[str, object], None]) -> None:
    from tests.ocr_fixtures import ENGLISH, RUSSIAN, UZ_LATIN, recall

    assert IMAGE
    started = time.monotonic()
    result = IsolatedExecutor(IMAGE).extract(
        _scan(ENGLISH, UZ_LATIN, RUSSIAN), "pdf", ocr_languages=("eng", "uzb", "rus")
    )
    record_property("ocr_seconds_3_pages", round(time.monotonic() - started, 2))
    assert result.ocr is not None and result.ocr.status == "completed", result.ocr
    assert [s.page for s in result.sections] == [1, 2, 3]
    for section, lines in zip(result.sections, (ENGLISH, UZ_LATIN, RUSSIAN), strict=True):
        assert recall(lines, result.text[section.start : section.end]) >= 0.9


def test_png_photo_is_read_with_ocr() -> None:
    from tests.ocr_fixtures import RUSSIAN, page_image, png, recall

    assert IMAGE
    result = IsolatedExecutor(IMAGE).extract(
        png(page_image(RUSSIAN, skew=2)), "png", ocr_languages=("rus",)
    )
    assert result.ocr is not None and result.ocr.status == "completed"
    assert recall(RUSSIAN, result.text) >= 0.9 and result.sections[0].page is None


def test_oversized_scan_is_refused_not_truncated() -> None:
    from ezo_api.documents.executor.protocol import MAX_OCR_PAGES
    from tests.ocr_fixtures import ENGLISH

    assert IMAGE
    result = IsolatedExecutor(IMAGE).extract(
        _scan(*[ENGLISH] * (MAX_OCR_PAGES + 1)), "pdf", ocr_languages=("eng",)
    )
    assert result.needs_ocr and result.text == "" and result.sections == []
    assert result.ocr is not None and result.ocr.status == "page_limit"
    assert result.ocr.pages == MAX_OCR_PAGES + 1 and result.ocr.pages_read == 0


def test_scan_without_requested_ocr_only_reports_it() -> None:
    from tests.ocr_fixtures import ENGLISH

    assert IMAGE
    result = IsolatedExecutor(IMAGE).extract(_scan(ENGLISH), "pdf")
    assert result.needs_ocr and result.ocr is None


@pytest.mark.parametrize("kind", ["docx", "xlsx", "pptx"])
def test_office_to_pdf_in_the_isolated_workload(
    kind: str, record_property: Callable[[str, object], None]
) -> None:
    from pptx import Presentation
    from pypdf import PdfReader

    from tests.office_fixtures import official_letter_docx, report_xlsx

    assert IMAGE
    if kind == "docx":
        data = official_letter_docx()
    elif kind == "xlsx":
        data = report_xlsx()
    else:
        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[1]).shapes.title.text = "Fotosintez"
        output = io.BytesIO()
        deck.save(output)
        data = output.getvalue()
    before = names()
    started = time.monotonic()
    pdf, meta = IsolatedExecutor(IMAGE).convert_to_pdf(data, kind)  # type: ignore[arg-type]
    record_property(f"convert_seconds_{kind}", round(time.monotonic() - started, 2))
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == meta.pages >= 1
    assert "LibreOffice" in meta.engine
    if kind == "pptx":
        assert "Fotosintez" in reader.pages[0].extract_text()
    assert names() == before


def test_office_file_with_external_links_is_refused() -> None:
    from tests.office_fixtures import official_letter_docx, with_external_image

    assert IMAGE
    before = names()
    with pytest.raises(ExecutorError, match="processing_failed"):
        IsolatedExecutor(IMAGE).convert_to_pdf(with_external_image(official_letter_docx()), "docx")
    assert names() == before


def test_executor_image_has_exactly_the_reviewed_ocr_languages() -> None:
    assert IMAGE
    langs = subprocess.check_output(
        [
            DOCKER,
            "run",
            "--rm",
            "--network=none",
            "--entrypoint",
            "tesseract",
            IMAGE,
            "--list-langs",
        ],
        text=True,
    ).split()
    assert {"eng", "uzb", "uzb_cyrl", "rus", "osd"} <= set(langs)
