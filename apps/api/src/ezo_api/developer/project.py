"""A generated software project: parse the model's files, check them, pack them.

The model writes every file between markers::

    <<<FILE index.html>>>
    ...content...
    <<<END>>>

Markers are used instead of JSON because code is full of quotes and backslashes that models
often escape wrongly. Every path is checked (relative, no "..", no hidden or binary files, a
known text extension) and the size of each file and of the whole project is capped. Nothing in
a project is executed by EZO.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from dataclasses import dataclass, field

MAX_FILES = 40
MAX_FILE_BYTES = 300_000
MAX_PROJECT_BYTES = 1_500_000

TEXT_EXTENSIONS = frozenset(
    {
        ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".json",
        ".md", ".txt", ".py", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".env.example",
        ".svg", ".xml", ".csv", ".sql", ".sh", ".bat", ".ps1", ".java", ".kt", ".go", ".rs",
        ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".dart", ".swift", ".vue",
        ".svelte", ".gitignore", ".dockerfile", ".lock", ".mod", ".gradle",
    }
)  # fmt: skip
EXTENSIONLESS = frozenset(
    {"Dockerfile", "Makefile", "Procfile", "LICENSE", ".gitignore", ".dockerignore"}
)

_FILE = re.compile(r"^<<<FILE\s+(.+?)\s*>>>[ \t]*\r?\n(.*?)^<<<END>>>[ \t]*$", re.M | re.S)
_FENCE = re.compile(r"^\s*```[\w+-]*\s*\n(.*?)\n\s*```\s*$", re.S)
_SAFE_PART = re.compile(r"^[A-Za-z0-9._@+-][A-Za-z0-9._@+ -]{0,99}$")


class ProjectError(Exception):
    """The model's output is not a usable project. `message` is safe to show."""


@dataclass(slots=True)
class Project:
    files: dict[str, str]
    """path → text content, in the order the model wrote them."""
    skipped: list[str] = field(default_factory=list)
    """Paths that were refused (unsafe, unsupported or too large), for the honesty note."""

    @property
    def is_website(self) -> bool:
        return self.entry_html is not None

    @property
    def entry_html(self) -> str | None:
        """index.html at the top (or inside one folder such as public/), else any page."""
        pages = [p for p in self.files if p.lower().endswith((".html", ".htm"))]
        for preferred in ("index.html", "public/index.html", "src/index.html", "dist/index.html"):
            if preferred in self.files:
                return preferred
        return pages[0] if len(pages) == 1 else (min(pages, key=len) if pages else None)

    @property
    def size(self) -> int:
        return sum(len(v.encode("utf-8")) for v in self.files.values())


def safe_path(raw: str) -> str | None:
    """A clean relative POSIX path, or None when the path is unsafe or not a text file."""
    path = raw.strip().strip("`\"'").replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if not path or path.startswith("/") or ":" in path:
        return None
    path = posixpath.normpath(path)
    parts = path.split("/")
    if len(parts) > 6 or any(p in ("", ".", "..") or not _SAFE_PART.match(p) for p in parts):
        return None
    name = parts[-1]
    if any(p.startswith(".") and p not in EXTENSIONLESS for p in parts[:-1]):
        return None  # hidden folders such as .git/ or .github/
    lowered = name.lower()
    if name in EXTENSIONLESS or lowered.endswith(".env.example"):
        return path
    if name.startswith("."):
        return None
    ext = posixpath.splitext(lowered)[1]
    return path if ext in TEXT_EXTENSIONS else None


def _unfence(content: str) -> str:
    """Models sometimes wrap a file in a ``` fence inside the markers; drop it."""
    found = _FENCE.match(content)
    return found.group(1) if found else content


def parse_project(text: str) -> Project:
    files: dict[str, str] = {}
    skipped: list[str] = []
    total = 0
    for found in _FILE.finditer(text):
        raw_path, content = found.group(1), _unfence(found.group(2)).rstrip() + "\n"
        path = safe_path(raw_path)
        size = len(content.encode("utf-8"))
        if path is None or size > MAX_FILE_BYTES or total + size > MAX_PROJECT_BYTES:
            skipped.append(raw_path.strip()[:120])
            continue
        if path not in files and len(files) >= MAX_FILES:
            skipped.append(path)
            continue
        total += size - len(files.get(path, "").encode("utf-8"))
        files[path] = content
    if not files:
        raise ProjectError("The model did not return any project files.")
    return Project(files=files, skipped=skipped)


def merge(previous: dict[str, str], changed: Project, deleted: list[str]) -> Project:
    """An edit: the earlier files, with the changed ones replaced and deleted ones removed."""
    files = {p: c for p, c in previous.items() if p not in deleted}
    files.update(changed.files)
    if not files:
        raise ProjectError("The edit would leave the project empty.")
    return Project(files=files, skipped=changed.skipped)


_DELETE = re.compile(r"^<<<DELETE\s+(.+?)\s*>>>[ \t]*$", re.M)


def deleted_paths(text: str) -> list[str]:
    return [p for raw in _DELETE.findall(text) if (p := safe_path(raw))]


def to_zip(project: Project, folder: str) -> bytes:
    """The project as a ZIP with one top folder (so unpacking does not scatter files)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in project.files.items():
            info = zipfile.ZipInfo(f"{folder}/{path}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def from_zip(data: bytes) -> dict[str, str]:
    """Files of a project ZIP made by `to_zip` (the top folder removed)."""
    files: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist()[: MAX_FILES * 2]:
            if info.is_dir() or info.file_size > MAX_FILE_BYTES:
                continue
            parts = info.filename.split("/", 1)
            path = safe_path(parts[1] if len(parts) == 2 else parts[0])
            if path is not None:
                files[path] = archive.read(info).decode("utf-8", errors="replace")
    return files


_LINK = re.compile(
    r"<link\b[^>]*\brel=[\"']?stylesheet[\"']?[^>]*\bhref=[\"']([^\"'>]+)[\"'][^>]*>"
    r"|<link\b[^>]*\bhref=[\"']([^\"'>]+)[\"'][^>]*\brel=[\"']?stylesheet[\"']?[^>]*>",
    re.I,
)
_SCRIPT = re.compile(r"<script\b([^>]*)\bsrc=[\"']([^\"'>]+)[\"']([^>]*)>\s*</script>", re.I)


def _local(project: Project, base: str, href: str) -> str | None:
    if re.match(r"^[a-z][a-z0-9+.-]*:|^//", href, re.I):
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), href.split("?")[0]))
    return project.files.get(path)


def bundle_site(project: Project) -> str | None:
    """The entry page with its local stylesheets and scripts inlined: one file that opens
    anywhere (and is shown as a preview). None when the project has no web page."""
    entry = project.entry_html
    if entry is None:
        return None
    html = project.files[entry]

    deferred: list[str] = []

    def style(found: re.Match[str]) -> str:
        css = _local(project, entry, found.group(1) or found.group(2))
        if css is None:
            return found.group(0)
        return "<style>\n" + css.replace("</", "<\\/") + "</style>"

    def script(found: re.Match[str]) -> str:
        code = _local(project, entry, found.group(2))
        if code is None:
            return found.group(0)
        attrs = (found.group(1) + found.group(3)).strip()
        late = bool(re.search(r"\bdefer\b", attrs))
        attrs = re.sub(r"\s*\b(defer|async)\b", "", attrs).strip()
        opening = f"<script {attrs}>" if attrs else "<script>"
        inlined = opening + "\n" + code.replace("</script", "<\\/script") + "</script>"
        if late:  # a deferred script runs after the page is parsed: keep that order
            deferred.append(inlined)
            return ""
        return inlined

    page = _SCRIPT.sub(script, _LINK.sub(style, html))
    if deferred:
        tail = "\n".join(deferred)
        at = page.lower().rfind("</body>")
        page = page[:at] + tail + "\n" + page[at:] if at >= 0 else page + "\n" + tail
    return page
