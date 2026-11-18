"""The Developer Agent's project files: parsing, path safety, ZIP and the one-file website."""

from __future__ import annotations

import pytest

from ezo_api.developer.project import (
    MAX_FILES,
    ProjectError,
    bundle_site,
    deleted_paths,
    from_zip,
    merge,
    parse_project,
    safe_path,
    to_zip,
)
from ezo_api.developer.requests import is_build_request

SITE = """Mana loyiha.
<<<FILE index.html>>>
<!doctype html><html><head><link rel="stylesheet" href="style.css">
<script src="script.js" defer></script></head>
<body><h1>Kafe</h1><script src="https://cdn.example.com/x.js"></script></body></html>
<<<END>>>
<<<FILE style.css>>>
```css
h1 { color: gold; }
```
<<<END>>>
<<<FILE script.js>>>
document.querySelector("h1").textContent += "!";
<<<END>>>
<<<FILE ../../etc/passwd.txt>>>
nope
<<<END>>>
<<<FILE .git/config>>>
nope
<<<END>>>
<<<FILE photo.png>>>
binary
<<<END>>>
"""


def test_parse_keeps_safe_text_files_and_refuses_the_rest() -> None:
    project = parse_project(SITE)
    assert list(project.files) == ["index.html", "style.css", "script.js"]
    assert project.files["style.css"] == "h1 { color: gold; }\n"  # the ``` fence is dropped
    assert set(project.skipped) == {"../../etc/passwd.txt", ".git/config", "photo.png"}
    assert project.is_website and project.entry_html == "index.html"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("src/app.py", "src/app.py"),
        ("./README.md", "README.md"),
        ("Dockerfile", "Dockerfile"),
        (".env.example", ".env.example"),
        ("/abs/path.py", None),
        ("C:/win.py", None),
        ("a/../../b.py", None),
        (".env", None),
        ("run.exe", None),
    ],
)
def test_safe_path(raw: str, expected: str | None) -> None:
    assert safe_path(raw) == expected


def test_no_files_is_an_error_and_the_file_count_is_capped() -> None:
    with pytest.raises(ProjectError):
        parse_project("Sorry, I cannot.")
    many = "".join(f"<<<FILE f{i}.txt>>>\nx\n<<<END>>>\n" for i in range(MAX_FILES + 5))
    assert len(parse_project(many).files) == MAX_FILES


def test_zip_round_trip_and_edit_merge() -> None:
    project = parse_project(SITE)
    data = to_zip(project, "kafe")
    assert from_zip(data) == project.files
    edit = "<<<FILE style.css>>>\nh1 { color: blue; }\n<<<END>>>\n<<<DELETE script.js>>>\n"
    merged = merge(project.files, parse_project(edit), deleted_paths(edit))
    assert merged.files["style.css"] == "h1 { color: blue; }\n"
    assert "script.js" not in merged.files and "index.html" in merged.files


def test_bundle_inlines_local_css_and_js_but_not_remote_scripts() -> None:
    page = bundle_site(parse_project(SITE))
    assert page is not None
    assert "<style>\nh1 { color: gold; }" in page
    assert 'href="style.css"' not in page and 'src="script.js"' not in page
    # The deferred script now runs after the page body, as before.
    assert page.index("textContent") > page.index("<h1>Kafe</h1>")
    assert 'src="https://cdn.example.com/x.js"' in page
    assert bundle_site(parse_project("<<<FILE main.py>>>\nprint(1)\n<<<END>>>")) is None


@pytest.mark.parametrize(
    "text",
    [
        "Menga kafe uchun website tuzib ber",
        "sayt yasab ber",
        "Python'da kalkulyator dasturi yozib ber",
        "Telegram bot yozib ber, ob-havoni aytsin",
        "Build me a landing page for a bakery",
        "write a python script that renames files",
        "Сделай сайт для кафе",
        "o'yin yasab ber: ilon",
    ],
)
def test_build_requests(text: str) -> None:
    assert is_build_request(text)


@pytest.mark.parametrize(
    "text",
    [
        "https://example.org saytini tarjima qil",
        "o'quv dasturi tuzib ber",
        "Telegram botim ishlamayapti",
        "API kaliti qayerdan olaman",
        "kun.uz saytidan yangiliklar top",
        "bu kod nima qiladi?",
    ],
)
def test_not_build_requests(text: str) -> None:
    assert not is_build_request(text)
