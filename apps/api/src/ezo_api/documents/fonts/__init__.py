"""Bundled fonts (Liberation Sans, SIL OFL 1.1 — see OFL.txt)."""

from __future__ import annotations

from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent
REGULAR = FONT_DIR / "LiberationSans-Regular.ttf"
BOLD = FONT_DIR / "LiberationSans-Bold.ttf"
# The name written into PPTX/DOCX files: metric-compatible with Liberation Sans.
OFFICE_FONT = "Arial"
