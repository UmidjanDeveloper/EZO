"""Upload validation: extension + content sniffing, size limits, safe filenames.

The browser-declared MIME type is not trusted (Windows often reports CSV as
Excel); the real type is decided from the extension AND the file's bytes.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024
MAX_ZIP_ENTRIES = 5_000


class UploadRejectedError(Exception):
    """The file is not acceptable. `message` is safe to show to the user."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class FileKind:
    mime_type: str
    category: str  # pdf | docx | xlsx | csv | text | markdown | image


_TEXT_KINDS = {
    ".txt": FileKind("text/plain", "text"),
    ".md": FileKind("text/markdown", "markdown"),
    ".markdown": FileKind("text/markdown", "markdown"),
    ".csv": FileKind("text/csv", "csv"),
}
_IMAGE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}
_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ALLOWED_EXTENSIONS = [".pdf", ".docx", ".xlsx", *_TEXT_KINDS, *_IMAGE_SIGNATURES]


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """A display-safe filename: no directories, control characters or odd symbols."""
    name = unicodedata.normalize("NFKC", name or "")
    name = re.split(r"[\\/]", name)[-1]  # drop any path the client sent
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = "file"
    if len(name) > max_length:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: max_length - len(ext) - 1] + "." + ext
        else:
            name = name[:max_length]
    return name


def extension_of(filename: str) -> str:
    _, dot, ext = filename.lower().rpartition(".")
    return f".{ext}" if dot else ""


def _check_zip(data: bytes, required_member: str, label: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if len(infos) > MAX_ZIP_ENTRIES:
                raise UploadRejectedError("too_complex", f"The {label} file has too many parts.")
            if sum(info.file_size for info in infos) > MAX_ZIP_UNCOMPRESSED:
                raise UploadRejectedError(
                    "too_large", f"The {label} file is too large when unpacked."
                )
    except zipfile.BadZipFile as exc:
        raise UploadRejectedError(
            "corrupt", f"The {label} file is damaged or not really {label}."
        ) from exc
    if required_member not in names:
        raise UploadRejectedError("wrong_type", f"The file is not a real {label} document.")


def _check_text(data: bytes) -> None:
    if b"\x00" in data[:8192]:
        raise UploadRejectedError("wrong_type", "The file does not look like text.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            data.decode("cp1251")  # common for older Russian/Uzbek Cyrillic files
        except UnicodeDecodeError as exc:
            raise UploadRejectedError(
                "encoding", "The text file encoding is not supported (use UTF-8)."
            ) from exc


def detect_kind(filename: str, data: bytes) -> FileKind:
    """Decide the file type from extension + bytes, or raise UploadRejectedError."""
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted({e.lstrip(".").upper() for e in ALLOWED_EXTENSIONS}))
        raise UploadRejectedError(
            "unsupported_type", f"This file type is not supported. Allowed: {allowed}."
        )
    if not data:
        raise UploadRejectedError("empty", "The file is empty.")

    if ext == ".pdf":
        if not data.lstrip()[:5] == b"%PDF-":
            raise UploadRejectedError("wrong_type", "The file is not a real PDF.")
        return FileKind("application/pdf", "pdf")
    if ext == ".docx":
        _check_zip(data, "word/document.xml", "Word (DOCX)")
        return FileKind(DOCX_MIME, "docx")
    if ext == ".xlsx":
        _check_zip(data, "xl/workbook.xml", "Excel (XLSX)")
        return FileKind(XLSX_MIME, "xlsx")
    if ext in _TEXT_KINDS:
        _check_text(data)
        return _TEXT_KINDS[ext]
    signatures = _IMAGE_SIGNATURES[ext]
    if not any(data.startswith(sig) for sig in signatures) or (
        ext == ".webp" and data[8:12] != b"WEBP"
    ):
        raise UploadRejectedError("wrong_type", "The file is not a real image of that type.")
    return FileKind(_IMAGE_MIME[ext], "image")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
