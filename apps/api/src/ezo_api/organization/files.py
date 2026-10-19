"""Uploaded organization files: checked, cleaned and stored.

- Logo: any common image, re-encoded by EZO as a PNG (metadata dropped, at most 600 px).
- Template: a real .docx without macros or external links (`templates.check_template`).
- Example: .docx, .pdf, .txt or .md; its text is extracted and shortened. Examples are
  used only as style references; their contents are untrusted data.
"""

from __future__ import annotations

from dataclasses import dataclass

from ezo_api.knowledge.parsers import ParseError, parse
from ezo_api.knowledge.uploads import (
    UploadRejectedError,
    detect_kind,
    sanitize_filename,
    sha256_hex,
)
from ezo_api.organization.templates import TemplateError, check_template
from ezo_api.visual.images import ImageRejectedError, normalize_image

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_LOGO_BYTES = 5 * 1024 * 1024
EXAMPLE_CHARS = 6_000
EXAMPLE_KINDS = ("docx", "pdf", "text", "markdown")


class OrgFileError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CheckedFile:
    filename: str
    mime_type: str
    data: bytes
    sha256: str
    text_excerpt: str | None = None


def check_logo(filename: str, data: bytes) -> CheckedFile:
    if len(data) > MAX_LOGO_BYTES:
        raise OrgFileError("too_large", "The logo is larger than 5 MB.")
    try:
        clean = normalize_image(data, max_side=600)
    except ImageRejectedError as exc:
        raise OrgFileError("bad_image", str(exc)) from exc
    return CheckedFile("logo.png", "image/png", clean.data, sha256_hex(clean.data))


def check_template_file(filename: str, data: bytes) -> CheckedFile:
    name = sanitize_filename(filename)
    if len(data) > MAX_FILE_BYTES:
        raise OrgFileError("too_large", "The file is larger than 10 MB.")
    try:
        kind = detect_kind(name, data)
    except UploadRejectedError as exc:
        raise OrgFileError(exc.code, exc.message) from exc
    if kind.category != "docx":
        raise OrgFileError("wrong_type", "A template must be a Word (.docx) file.")
    try:
        check_template(data)
    except TemplateError as exc:
        raise OrgFileError("bad_template", exc.message) from exc
    return CheckedFile(name, kind.mime_type, data, sha256_hex(data))


def check_example_file(filename: str, data: bytes) -> CheckedFile:
    name = sanitize_filename(filename)
    if len(data) > MAX_FILE_BYTES:
        raise OrgFileError("too_large", "The file is larger than 10 MB.")
    try:
        kind = detect_kind(name, data)
    except UploadRejectedError as exc:
        raise OrgFileError(exc.code, exc.message) from exc
    if kind.category not in EXAMPLE_KINDS:
        raise OrgFileError("wrong_type", "An example must be a Word, PDF, text or Markdown file.")
    try:
        text = parse(kind.category, data, name).text.strip()
    except ParseError as exc:
        raise OrgFileError("unreadable", f"The file could not be read: {exc}") from exc
    if not text:
        raise OrgFileError("no_text", "The file has no text (a scan needs OCR first).")
    return CheckedFile(name, kind.mime_type, data, sha256_hex(data), text[:EXAMPLE_CHARS])
