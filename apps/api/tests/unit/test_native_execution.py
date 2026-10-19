"""Real local child processes exercise capture budgets, deadlines and descendants."""

import io
import os
import signal
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest

from ezo_api.documents import office_convert, process_limits
from ezo_api.documents.ocr import tesseract
from ezo_api.documents.ocr.model import OCRError


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_ocr_stops_output_flood_before_execution_timeout(
    monkeypatch: pytest.MonkeyPatch, stream: str
) -> None:
    monkeypatch.setattr(tesseract, "MAX_OUTPUT_BYTES", 1024)
    code = (
        f"import sys,time; sys.{stream}.buffer.write(b'x'*65536); "
        f"sys.{stream}.flush(); time.sleep(10)"
    )
    with pytest.raises(OCRError) as error:
        tesseract._run([sys.executable, "-c", code], b"", 1)
    assert error.value.code == "output_limit"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process group state checks")
@pytest.mark.parametrize("parent_exits", [False, True])
def test_ocr_cleans_descendants_on_timeout_and_success(tmp_path: Path, parent_exits: bool) -> None:
    pidfile = tmp_path / "child.pid"
    code = (
        "import subprocess,sys,time; from pathlib import Path; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        f"Path({str(pidfile)!r}).write_text(str(p.pid)); "
        + ("sys.exit(0)" if parent_exits else "time.sleep(30)")
    )
    try:
        if parent_exits:
            assert tesseract._run([sys.executable, "-c", code], b"", 1) == b""
        else:
            with pytest.raises(OCRError) as error:
                tesseract._run([sys.executable, "-c", code], b"", 1)
            assert error.value.code == "timeout"
        assert pidfile.exists(), "fixture must actually start a descendant"
        pid = int(pidfile.read_text())
        for _ in range(40):
            if not _running(pid):
                break
            time.sleep(0.025)
        assert not _running(pid), "native descendant survived the operation"
    finally:
        if pidfile.exists() and _running(pid := int(pidfile.read_text())):
            os.kill(pid, signal.SIGKILL)  # fixture cleanup even before the regression is fixed


def _running(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        return state != "Z"
    except FileNotFoundError:
        return False


def test_native_queue_wait_is_inside_the_operation_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = threading.Lock()
    lock.acquire()
    monkeypatch.setattr(process_limits, "NATIVE_PROCESS_LOCK", lock)
    monkeypatch.setattr(tesseract, "NATIVE_PROCESS_LOCK", lock, raising=False)
    release = threading.Timer(1.5, lock.release)
    release.start()
    try:
        with pytest.raises(OCRError) as error:
            tesseract._run([sys.executable, "-c", "print('ok')"], b"", 0.1)
        assert error.value.code == "timeout"
    finally:
        release.cancel()
        release.join()
        if lock.locked():
            lock.release()


@pytest.mark.skipif(os.name != "posix", reason="local executable fixture")
def test_office_stops_diagnostic_flood_before_timeout(tmp_path: Path) -> None:
    binary = tmp_path / "fake-office"
    binary.write_text(
        f"#!{sys.executable}\nimport sys,time\n"
        "sys.stderr.buffer.write(b'x'*262144)\nsys.stderr.flush()\ntime.sleep(10)\n"
    )
    binary.chmod(0o755)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("_rels/.rels", "<Relationships/>")
    converter = office_convert.OfficeConverter(str(binary), "fixture", timeout_seconds=1)
    with pytest.raises(office_convert.OfficeConvertError) as error:
        converter.to_pdf_sync(buffer.getvalue(), "docx")
    assert error.value.code == "output_limit"
