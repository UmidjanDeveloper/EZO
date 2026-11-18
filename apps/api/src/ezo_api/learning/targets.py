"""What the user asked EZO to learn: a website, a GitHub repository or a package.

Recognised forms (in a chat message or the API):
- https://github.com/owner/repo (also /tree/branch…), github:owner/repo
- https://pypi.org/project/name, pypi:name, "pip install name"
- https://www.npmjs.com/package/name, npm:name, "npm install name"
- any other http(s) URL: a website (documentation) to read within its folder
- plain words: "fastapi kutubxonasini o'rgan", "npm axios paketini o'rgan", "React library",
  "owner/repo repozitoriyasini o'rgan" (a package on PyPI unless npm/JavaScript is named or
  the name is a well-known npm package; a bare owner/repo next to a repository word)
Nothing is fetched here; `knowledge.fetch.validate_url` and the SafeFetcher check every
address before it is opened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

KINDS = ("website", "github", "pypi", "npm")

_GITHUB_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
_REPO_NAME = r"[A-Za-z0-9._-]{1,100}"
_PYPI_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})"
_NPM_NAME = r"(?:@[a-z0-9][a-z0-9._-]{0,100}/)?[a-z0-9][a-z0-9._-]{0,213}"

_GITHUB_URL = re.compile(
    rf"https?://(?:www\.)?github\.com/({_GITHUB_NAME})/({_REPO_NAME})(?:[/#?]\S*)?", re.I
)
_GITHUB_ID = re.compile(rf"(?<![\w/])github:({_GITHUB_NAME})/({_REPO_NAME})", re.I)
_PYPI_URL = re.compile(rf"https?://pypi\.org/project/({_PYPI_NAME})/?", re.I)
_PYPI_ID = re.compile(rf"(?<![\w/])(?:pypi:|pip install\s+)({_PYPI_NAME})", re.I)
_NPM_URL = re.compile(rf"https?://(?:www\.)?npmjs\.com/package/({_NPM_NAME})/?", re.I)
_NPM_ID = re.compile(rf"(?<![\w/])(?:npm:|npm (?:install|i)\s+)({_NPM_NAME})", re.I)
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.I)

# "fastapi kutubxonasini", "npm axios paketini", "the httpx library", "библиотеку requests".
_PACKAGE_WORD = (
    r"(?:kutubxona|kutibxona|kutubhona|paket|package|library|librar|framework|freymvork|"
    r"библиотек|пакет|фреймворк|кутубхона)"
)
_ECOSYSTEM = r"(?:(npm|node|js|javascript|pip|pypi|python)\s+)?"
_NATURAL_BEFORE = re.compile(
    rf"(?<![\w@/.:-]){_ECOSYSTEM}(@?[a-z0-9][a-z0-9._/-]{{0,80}})\s+{_PACKAGE_WORD}", re.I
)
_NATURAL_AFTER = re.compile(
    rf"{_PACKAGE_WORD}\w*[:\s]+{_ECOSYSTEM}(@?[a-z0-9][a-z0-9._/-]{{0,80}})(?![\w-])", re.I
)
_REPO_WORD = r"(?:repo\w*|repozitor\w*|репозитор\w*)"
_BARE_REPO = re.compile(
    rf"(?<![\w/.:@-])({_GITHUB_NAME})/({_REPO_NAME})(?:\s+{_REPO_WORD})|"
    rf"{_REPO_WORD}\s+({_GITHUB_NAME})/({_REPO_NAME})(?![\w/])",
    re.I,
)
# Words that can stand before "kutubxona" without naming a package.
_NOT_A_PACKAGE = frozenset(
    "bu shu ushbu mana o'sha osha shunday this that the a an my your our their his her its "
    "mening sening uning bizning sizning ularning yangi kerakli barcha hamma butun asosiy "
    "standart standard python javascript js node npm pip pypi typescript ts go rust java "
    "kotlin swift php ruby dart c c++ c# ezo bilim knowledge kod code bitta har qaysi qanday "
    "этот эту эта мою твою нашу новую всю python-ning nodejs".split()
)
# Names that are npm packages even when the user does not say "npm".
_NPM_FAMOUS = frozenset(
    "react react-dom next vue nuxt angular svelte express axios lodash jquery three d3 "
    "chart.js tailwindcss vite webpack typescript prisma mongoose socket.io redux zustand "
    "electron nestjs @nestjs/core koa fastify moment dayjs zod".split()
)


def _natural_package(text: str) -> Target | None:
    for pattern in (_NATURAL_BEFORE, _NATURAL_AFTER):
        for found in pattern.finditer(text):
            ecosystem = (found.group(1) or "").lower()
            name = _strip(found.group(2)).lower()
            name = re.sub(r"(ni|ning|ga|da|dan)$", "", name) if "'" not in name else name
            if not name or name in _NOT_A_PACKAGE or len(name) < 2 or name.isdigit():
                continue
            npm = ecosystem in ("npm", "node", "js", "javascript") or (
                not ecosystem and name in _NPM_FAMOUS
            )
            if npm:
                if not re.fullmatch(_NPM_NAME, name):
                    continue
                return Target("npm", name, f"https://www.npmjs.com/package/{name}")
            if "/" in name or name.startswith("@") or not re.fullmatch(_PYPI_NAME, name):
                continue
            return Target("pypi", name, f"https://pypi.org/project/{name}/")
    return None


@dataclass(frozen=True, slots=True)
class Target:
    kind: str
    identifier: str
    """github: owner/repo; pypi / npm: package name; website: the canonical URL."""
    url: str
    """A human-facing URL for the source."""

    @property
    def key(self) -> str:
        """Stable registry key (one learned source per key and library)."""
        return self.url if self.kind == "website" else f"{self.kind}:{self.identifier}"


def canonical_url(url: str) -> str:
    """Lower-case scheme and host, no fragment, no default port, '/' for an empty path."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


def _strip(url: str) -> str:
    return url.rstrip(".,;:!?)]}»”'\"")


def parse_target(text: str) -> Target | None:
    """The first learnable source named in `text`, or None."""
    text = text.strip()
    if found := _GITHUB_URL.search(text) or _GITHUB_ID.search(text):
        owner, repo = found.group(1), _strip(found.group(2))
        repo = repo.removesuffix(".git")
        return Target("github", f"{owner}/{repo}", f"https://github.com/{owner}/{repo}")
    if found := _PYPI_URL.search(text) or _PYPI_ID.search(text):
        name = _strip(found.group(1))
        return Target("pypi", name.lower(), f"https://pypi.org/project/{name}/")
    if found := _NPM_URL.search(text) or _NPM_ID.search(text):
        name = _strip(found.group(1)).lower()
        return Target("npm", name, f"https://www.npmjs.com/package/{name}")
    if found := _URL.search(text):
        url = canonical_url(_strip(found.group(0)))
        return Target("website", url, url)
    if found := _BARE_REPO.search(text):
        owner = found.group(1) or found.group(3)
        repo = _strip(found.group(2) or found.group(4)).removesuffix(".git")
        return Target("github", f"{owner}/{repo}", f"https://github.com/{owner}/{repo}")
    return _natural_package(text)


def parse_key(kind: str, value: str) -> Target | None:
    """Target from an explicit API value ("pypi:requests", a URL…)."""
    target = parse_target(value)
    if target is None and kind in ("pypi", "npm", "github"):
        target = parse_target(f"{kind}:{value}")
    if target is None or (kind and kind != "auto" and target.kind != kind):
        return None
    return target
