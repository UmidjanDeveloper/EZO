"""Reading a GitHub repository without running anything from it.

1. Metadata from the GitHub REST API (description, default branch, licence, latest
   commit, latest release) and the file tree of that commit. An optional token
   (EZO_GITHUB_TOKEN) raises the API limit and gives access to the owner's private
   repositories; it is sent only to api.github.com.
2. Files are chosen by priority — README, licence, manifests, docs, API specifications,
   then (if allowed) examples, entry points and tests — within the budget, and read as
   text from raw.githubusercontent.com at that exact commit.
3. When the API is unavailable (limit reached, blocked network), EZO falls back to
   reading well-known files at the default branch (HEAD) and says so: the commit is then
   unknown.
Nothing is cloned, installed or executed: no archives, no install scripts.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from ezo_api.knowledge.fetch import FetchError, SafeFetcher
from ezo_api.learning.base import Budget, Inspection, ReadDocument
from ezo_api.learning.safety import normalize_license

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

TEXT_EXTENSIONS = (
    ".md", ".mdx", ".rst", ".txt", ".adoc", ".toml", ".cfg", ".ini", ".yaml", ".yml",
    ".json", ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp", ".swift", ".sh",
    ".sql", ".proto", ".graphql",
)  # fmt: skip
SKIP_DIRS = (
    "node_modules/", "vendor/", "third_party/", "dist/", "build/", ".git/", "site-packages/",
    "__pycache__/", ".venv/", "venv/",
)  # fmt: skip
MANIFESTS = (
    "pyproject.toml", "setup.cfg", "package.json", "cargo.toml", "go.mod", "pom.xml",
    "build.gradle", "composer.json", "gemfile", "requirements.txt", "environment.yml",
)  # fmt: skip
FALLBACK_FILES = (
    "README.md", "README.rst", "README.txt", "README", "LICENSE", "LICENSE.md", "LICENSE.txt",
    "COPYING", "pyproject.toml", "setup.cfg", "package.json", "Cargo.toml", "go.mod",
    "CHANGELOG.md", "docs/index.md", "docs/README.md",
)  # fmt: skip
_OPENAPI = re.compile(r"(openapi|swagger)[^/]*\.(ya?ml|json)$", re.I)


def priority(path: str, include_code: bool) -> int | None:
    """Lower is read first; None means not read."""
    lowered = path.lower()
    name = lowered.rsplit("/", 1)[-1]
    if any(f"/{d}" in f"/{lowered}" for d in SKIP_DIRS):
        return None
    depth = lowered.count("/")
    if depth == 0 and name.startswith("readme"):
        return 0
    if depth == 0 and name.startswith(("license", "licence", "copying")):
        return 1
    if depth == 0 and name in MANIFESTS:
        return 2
    if _OPENAPI.search(lowered):
        return 3
    if not lowered.endswith(TEXT_EXTENSIONS) and name not in ("readme", "license", "copying"):
        return None
    is_doc = lowered.endswith((".md", ".mdx", ".rst", ".txt", ".adoc"))
    if lowered.startswith(("docs/", "doc/", "documentation/")) and is_doc:
        return 4
    if depth == 0 and is_doc:
        return 5  # CHANGELOG, CONTRIBUTING, SECURITY…
    if not include_code:
        return None
    if lowered.startswith(("examples/", "example/", "samples/")):
        return 6
    entry = ("__init__.py", "index.ts", "index.js", "main.py", "main.go", "lib.rs", "mod.rs")
    if name in entry and depth <= 2:
        return 7
    if lowered.startswith(("tests/", "test/")) and depth <= 2:
        return 9
    if depth == 1 or (depth == 2 and lowered.startswith("src/")):
        return 8  # top-level package modules
    return None


def _category(path: str) -> str:
    lowered = path.lower()
    return "markdown" if lowered.endswith((".md", ".mdx")) else "text"


def _decode_json(page_data: bytes) -> Any:
    return json.loads(page_data.decode("utf-8", errors="replace"))


class GitHubReader:
    def __init__(self, fetcher: SafeFetcher, token: str | None = None) -> None:
        self.fetcher = fetcher
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _api(self, path: str, max_bytes: int = 2_000_000) -> Any:
        page = await self.fetcher.fetch_json(f"{API}{path}", max_bytes, headers=self._headers())
        return _decode_json(page.data)

    async def read(self, identifier: str, budget: Budget, inspection: Inspection) -> None:
        owner, repo = identifier.split("/", 1)
        base = f"/repos/{quote(owner)}/{quote(repo)}"
        try:
            meta = await self._api(base)
        except FetchError as exc:
            reason = (
                "the GitHub API limit was reached or access was refused"
                if exc.status in (403, 429)
                else "the repository was not found or is private"
                if exc.status == 404
                else exc.message
            )
            if exc.status == 404:
                inspection.errors.append(f"GitHub: {reason}.")
                inspection.profile["access"] = "not_found_or_private"
                return
            inspection.profile["access"] = "raw_fallback"
            inspection.profile["access_note"] = (
                f"GitHub API unavailable ({reason}); read well-known files at the default "
                "branch instead. The exact commit is unknown."
            )
            await self._fallback(owner, repo, budget, inspection)
            return

        branch = str(meta.get("default_branch") or "HEAD")
        inspection.title = str(meta.get("full_name") or identifier)
        license_info = meta.get("license") or {}
        inspection.license = normalize_license(
            license_info.get("spdx_id") if isinstance(license_info, dict) else None
        )
        inspection.profile.update(
            {
                "access": "api",
                "publisher": (meta.get("owner") or {}).get("login"),
                "description": meta.get("description"),
                "homepage": meta.get("homepage") or None,
                "topics": meta.get("topics") or [],
                "default_branch": branch,
                "stars": meta.get("stargazers_count"),
                "archived": bool(meta.get("archived")),
                "private": bool(meta.get("private")),
                "last_push": meta.get("pushed_at"),
                "language": meta.get("language"),
            }
        )
        sha = branch
        try:
            branch_info = await self._api(f"{base}/branches/{quote(branch)}")
            sha = str(branch_info["commit"]["sha"])
            inspection.profile["commit"] = sha
        except (FetchError, KeyError, TypeError):
            inspection.errors.append("The latest commit could not be read; HEAD was used.")
        try:
            release = await self._api(f"{base}/releases/latest")
            inspection.profile["latest_release"] = release.get("tag_name")
        except FetchError:
            inspection.profile["latest_release"] = None
        # The files are read at this commit, so the commit is the version; the latest
        # release tag (which may be older than the branch) stays in the profile.
        inspection.version = sha[:12] if sha != branch else None

        try:
            tree = await self._api(f"{base}/git/trees/{quote(sha)}?recursive=1", 8_000_000)
        except FetchError as exc:
            inspection.errors.append(f"The file list could not be read ({exc.message}).")
            await self._fallback(owner, repo, budget, inspection, ref=sha)
            return
        files = [
            (str(item.get("path")), int(item.get("size") or 0))
            for item in tree.get("tree", [])
            if item.get("type") == "blob"
        ]
        inspection.profile["files_total"] = len(files)
        inspection.profile["tree_truncated"] = bool(tree.get("truncated"))
        inspection.profile["structure"] = _structure(files)
        inspection.profile["entry_points"] = [
            path for path, _ in files if priority(path, True) in (2, 3, 7)
        ][:20]
        ranked = sorted(
            (
                (p, path, size)
                for path, size in files
                if (p := priority(path, budget.limits.include_code)) is not None
            ),
            key=lambda item: (item[0], item[1].count("/"), item[1]),
        )
        for _, path, size in ranked:
            if stop := budget.over():
                inspection.stopped = stop
                break
            if size > budget.limits.max_file_kb * 1024:
                inspection.skip(path, "too_large")
                continue
            await self._read_file(owner, repo, sha, path, budget, inspection)

    async def _read_file(
        self, owner: str, repo: str, ref: str, path: str, budget: Budget, inspection: Inspection
    ) -> bool:
        url = f"{RAW}/{quote(owner)}/{quote(repo)}/{quote(ref)}/{quote(path)}"
        try:
            budget.requests += 1
            page = await self.fetcher.fetch(url, max_bytes=budget.limits.max_file_kb * 1024)
        except FetchError as exc:
            inspection.skip(path, exc.code)
            return False
        budget.documents += 1
        budget.bytes += len(page.data)
        inspection.documents.append(
            ReadDocument(
                url=f"https://github.com/{owner}/{repo}/blob/{ref}/{path}",
                title=f"{owner}/{repo}: {path}",
                filename=path.replace("/", "_")[:150],
                category=_category(path),
                data=page.data,
                meta={"path": path, "ref": ref},
            )
        )
        return True

    async def _fallback(
        self, owner: str, repo: str, budget: Budget, inspection: Inspection, ref: str = "HEAD"
    ) -> None:
        inspection.title = inspection.title or f"{owner}/{repo}"
        have: set[str] = set()  # "readme", "license": one of each spelling is enough
        for path in FALLBACK_FILES:
            if reason := budget.over():
                inspection.stopped = reason
                break
            lowered = path.lower()
            group = (
                "readme"
                if lowered.startswith("readme")
                else "license"
                if lowered.startswith(("license", "copying"))
                else lowered
            )
            if group in have:
                continue
            if await self._read_file(owner, repo, ref, path, budget, inspection):
                have.add(group)
                if group == "license" and inspection.license is None:
                    inspection.license = license_from_text(inspection.documents[-1].data)
        # Missing optional files (404) are expected here and not worth reporting.
        inspection.skipped = [
            s
            for s in inspection.skipped
            if not (s["reason"] == "http" and s["url"] in FALLBACK_FILES)
        ]
        if not inspection.documents:
            inspection.errors.append("No files could be read from this repository.")


def license_from_text(data: bytes) -> str | None:
    """A licence name from the first lines of a LICENSE file (best effort)."""
    head = data[:3000].decode("utf-8", errors="replace").lower()
    checks = (
        ("gnu affero general public license", "agpl-3.0"),
        ("gnu lesser general public license", "lgpl-3.0"),
        ("gnu general public license", "gpl-3.0" if "version 3" in head else "gpl-2.0"),
        ("mozilla public license", "mpl-2.0"),
        ("apache license", "apache-2.0"),
        ("mit license", "mit"),
        ("permission is hereby granted, free of charge", "mit"),
        ("redistribution and use in source and binary forms", "bsd-3-clause"),
        ("isc license", "isc"),
        ("this is free and unencumbered software", "unlicense"),
    )
    for needle, spdx in checks:
        if needle in head:
            return spdx
    return None


def _structure(files: list[tuple[str, int]]) -> list[dict[str, int | str]]:
    """Top-level folders and how many files each holds (a map of the repository)."""
    counts: dict[str, int] = {}
    for path, _ in files:
        top = path.split("/", 1)[0] if "/" in path else "."
        counts[top] = counts.get(top, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:25]
    return [{"folder": folder, "files": count} for folder, count in ordered]
