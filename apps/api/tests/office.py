"""Optional independent validation: convert a file with LibreOffice (if installed)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
requires_office = pytest.mark.skipif(SOFFICE is None, reason="LibreOffice is not installed")


def office_to_pdf(data: bytes, suffix: str) -> bytes:
    """Open the file in LibreOffice headless and export it to PDF; fails if it cannot be opened."""
    assert SOFFICE is not None
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"input{suffix}"
        source.write_bytes(data)
        subprocess.run(  # noqa: S603 - fixed binary, temporary paths only
            [
                SOFFICE,
                "--headless",
                f"-env:UserInstallation=file://{tmp}/profile",
                "--convert-to",
                "pdf",
                "--outdir",
                tmp,
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        output = Path(tmp) / "input.pdf"
        assert output.exists(), "LibreOffice could not convert the file"
        return output.read_bytes()
