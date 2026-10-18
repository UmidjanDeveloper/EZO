import io
import zipfile

import pytest

from ezo_api.knowledge.uploads import UploadRejectedError, detect_kind, sanitize_filename
from tests.files import PNG_1PX, make_docx, make_pdf, make_xlsx


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\secret.docx", "secret.docx"),
        ("hisobot 2026 (yakuniy).pdf", "hisobot 2026 (yakuniy).pdf"),
        ("отчёт.xlsx", "отчёт.xlsx"),
        ("bad<>:|?*name.txt", "bad_name.txt"),
        ("", "file"),
        ("....", "file"),
        ("a\x00b\x1f.txt", "ab.txt"),
    ],
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_long_filenames_keep_extension() -> None:
    name = sanitize_filename("x" * 400 + ".pdf")
    assert len(name) <= 150 and name.endswith(".pdf")


@pytest.mark.parametrize(
    ("filename", "data", "category"),
    [
        ("a.pdf", make_pdf(["Salom"]), "pdf"),
        ("a.docx", make_docx("T", ["p"]), "docx"),
        ("a.xlsx", make_xlsx([["a", 1]]), "xlsx"),
        ("a.csv", b"name,score\nAli,5\n", "csv"),
        ("a.txt", "Matn o‘zbekcha".encode(), "text"),
        ("a.md", b"# Title\n\ntext", "markdown"),
        ("a.png", PNG_1PX, "image"),
        ("old.txt", "Привет".encode("cp1251"), "text"),
    ],
)
def test_valid_files(filename: str, data: bytes, category: str) -> None:
    assert detect_kind(filename, data).category == category


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("filename", "data", "code"),
    [
        ("virus.exe", b"MZ\x90\x00", "unsupported_type"),
        ("noext", b"hello", "unsupported_type"),
        ("fake.pdf", b"just text pretending", "wrong_type"),
        ("fake.png", b"%PDF-1.4 not an image", "wrong_type"),
        ("fake.docx", _zip({"random.txt": b"x"}), "wrong_type"),
        ("broken.xlsx", b"PK\x03\x04garbage", "corrupt"),
        ("bin.txt", b"abc\x00\x01\x02", "wrong_type"),
        ("empty.txt", b"", "empty"),
    ],
)
def test_rejected_files(filename: str, data: bytes, code: str) -> None:
    with pytest.raises(UploadRejectedError) as info:
        detect_kind(filename, data)
    assert info.value.code == code
    assert info.value.message  # human-readable


def test_macro_payloads_in_office_files_are_refused() -> None:
    import io
    import zipfile

    from tests.docx_fixtures import rich_docx

    source = zipfile.ZipFile(io.BytesIO(rich_docx()))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr("word/vbaProject.bin", b"\x00macro")
    with pytest.raises(UploadRejectedError) as caught:
        detect_kind("renamed.docx", buffer.getvalue())
    assert caught.value.code == "macros"
    assert detect_kind("clean.docx", rich_docx()).category == "docx"
