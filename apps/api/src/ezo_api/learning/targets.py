"""What the user asked EZO to learn: a website, a GitHub repository or a package.

Recognised forms (in a chat message or the API):
- https://github.com/owner/repo (also /tree/branch…), github:owner/repo
- https://pypi.org/project/name, pypi:name, "pip install name"
- https://www.npmjs.com/package/name, npm:name, "npm install name"
- any other http(s) URL: a website (documentation) to read within its folder
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
    return None


def parse_key(kind: str, value: str) -> Target | None:
    """Target from an explicit API value ("pypi:requests", a URL…)."""
    target = parse_target(value)
    if target is None and kind in ("pypi", "npm", "github"):
        target = parse_target(f"{kind}:{value}")
    if target is None or (kind and kind != "auto" and target.kind != kind):
        return None
    return target
