"""Reading a package from PyPI or npm: registry metadata, its README and (when the
package links one) its documentation website, all within one budget.

The registry APIs are public JSON endpoints (no key). Nothing is downloaded from the
package itself: no wheels, tarballs or install scripts.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlsplit

from ezo_api.knowledge.fetch import FetchError, SafeFetcher
from ezo_api.learning.base import Budget, Inspection, ReadDocument
from ezo_api.learning.crawler import crawl
from ezo_api.learning.safety import normalize_license

PYPI = "https://pypi.org/pypi"
NPM = "https://registry.npmjs.org"
_DOC_KEYS = ("documentation", "docs", "doc")


def _json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8", errors="replace"))


def _facts(title: str, rows: list[tuple[str, Any]]) -> bytes:
    """A small Markdown page with the package's facts (written by EZO from metadata)."""
    lines = [f"# {title}", ""]
    for label, value in rows:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            lines.append(f"## {label}")
            lines.extend(f"- {item}" for item in value[:80])
            lines.append("")
        else:
            lines.append(f"**{label}:** {value}")
            lines.append("")
    return "\n".join(lines).encode("utf-8")


def _add(budget: Budget, inspection: Inspection, document: ReadDocument) -> None:
    budget.documents += 1
    budget.bytes += len(document.data)
    inspection.documents.append(document)


def _docs_url(urls: dict[str, str]) -> str | None:
    for key, value in urls.items():
        if key.strip().lower() in _DOC_KEYS and str(value).startswith(("http://", "https://")):
            return str(value)
    return None


async def _read_docs(
    fetcher: SafeFetcher, url: str | None, budget: Budget, inspection: Inspection
) -> None:
    if not url or budget.over():
        return
    host = urlsplit(url).netloc.lower()
    if host in ("pypi.org", "www.npmjs.com", "github.com"):
        return  # not a documentation site
    before = len(inspection.documents)
    errors = len(inspection.errors)
    await crawl(fetcher, url, budget, inspection)
    read = len(inspection.documents) - before
    inspection.profile["docs_site"] = {"url": url, "pages_read": read}
    if read == 0 and len(inspection.errors) > errors:
        # The package was read, its documentation website was not: the source is partial.
        message = inspection.errors.pop()
        inspection.profile["docs_site"]["error"] = message
        inspection.errors.append(f"The documentation website {url} could not be read: {message}")


async def read_pypi(
    fetcher: SafeFetcher, name: str, budget: Budget, inspection: Inspection
) -> None:
    try:
        page = await fetcher.fetch_json(f"{PYPI}/{quote(name)}/json", max_bytes=20_000_000)
    except FetchError as exc:
        inspection.errors.append(
            f"PyPI: package “{name}” was not found."
            if exc.status == 404
            else f"PyPI could not be read: {exc.message}"
        )
        return
    budget.requests += 1
    data = _json(page.data)
    info: dict[str, Any] = data.get("info") or {}
    version = str(info.get("version") or "") or None
    classifiers = [str(c) for c in info.get("classifiers") or []]
    license_value = (
        info.get("license_expression")
        or next((c for c in classifiers if c.startswith("License ::")), None)
        or (info.get("license") if len(str(info.get("license") or "")) < 100 else None)
    )
    urls = {str(k): str(v) for k, v in (info.get("project_urls") or {}).items()}
    released = next(
        (u.get("upload_time_iso_8601") for u in data.get("urls") or [] if isinstance(u, dict)),
        None,
    )
    inspection.title = str(info.get("name") or name)
    inspection.version = version
    inspection.license = normalize_license(str(license_value) if license_value else None)
    inspection.profile.update(
        {
            "access": "api",
            "publisher": info.get("author") or info.get("maintainer") or None,
            "description": info.get("summary"),
            "homepage": info.get("home_page") or urls.get("Homepage") or None,
            "links": urls,
            "requires_python": info.get("requires_python"),
            "dependencies": [str(d) for d in info.get("requires_dist") or []][:100],
            "released": released,
            "yanked": bool(info.get("yanked")),
            "repository": next(
                (v for k, v in urls.items() if k.lower() in ("source", "repository", "code")),
                None,
            ),
        }
    )
    _add(
        budget,
        inspection,
        ReadDocument(
            url=f"https://pypi.org/project/{inspection.title}/{version or ''}",
            title=f"{inspection.title} {version or ''} — PyPI facts".strip(),
            filename=f"{inspection.title}-pypi-facts.md",
            category="markdown",
            data=_facts(
                f"{inspection.title} {version or ''}".strip(),
                [
                    ("Summary", info.get("summary")),
                    ("Version", version),
                    ("Released", released),
                    ("Licence", inspection.license),
                    ("Requires Python", info.get("requires_python")),
                    ("Links", [f"{k}: {v}" for k, v in urls.items()]),
                    ("Dependencies", inspection.profile["dependencies"]),
                    ("Classifiers", classifiers[:40]),
                ],
            ),
            meta={"kind": "registry_facts"},
        ),
    )
    description = str(info.get("description") or "").strip()
    if description and description.upper() != "UNKNOWN":
        markdown = "markdown" in str(info.get("description_content_type") or "")
        _add(
            budget,
            inspection,
            ReadDocument(
                url=f"https://pypi.org/project/{inspection.title}/",
                title=f"{inspection.title} — README (PyPI)",
                filename=f"{inspection.title}-README.{'md' if markdown else 'txt'}",
                category="markdown" if markdown else "text",
                data=description.encode("utf-8")[: budget.limits.max_file_kb * 1024 * 4],
                meta={"kind": "readme"},
            ),
        )
    await _read_docs(fetcher, _docs_url(urls), budget, inspection)


async def read_npm(fetcher: SafeFetcher, name: str, budget: Budget, inspection: Inspection) -> None:
    encoded = quote(name, safe="@") if not name.startswith("@") else "@" + quote(name[1:], safe="")
    try:
        latest = _json((await fetcher.fetch_json(f"{NPM}/{encoded}/latest")).data)
    except FetchError as exc:
        inspection.errors.append(
            f"npm: package “{name}” was not found."
            if exc.status == 404
            else f"npm could not be read: {exc.message}"
        )
        return
    budget.requests += 1
    version = str(latest.get("version") or "") or None
    repository = latest.get("repository")
    repo_url = repository.get("url") if isinstance(repository, dict) else repository
    inspection.title = str(latest.get("name") or name)
    inspection.version = version
    license_value = latest.get("license")
    if isinstance(license_value, dict):
        license_value = license_value.get("type")
    inspection.license = normalize_license(str(license_value) if license_value else None)
    dependencies = [f"{k} {v}" for k, v in (latest.get("dependencies") or {}).items()]
    inspection.profile.update(
        {
            "access": "api",
            "publisher": (latest.get("author") or {}).get("name")
            if isinstance(latest.get("author"), dict)
            else latest.get("author"),
            "description": latest.get("description"),
            "homepage": latest.get("homepage"),
            "repository": repo_url,
            "dependencies": dependencies[:100],
            "entry_points": [
                str(v) for v in (latest.get("main"), latest.get("types"), latest.get("module")) if v
            ],
            "keywords": latest.get("keywords") or [],
        }
    )
    readme = ""
    try:
        full = _json((await fetcher.fetch_json(f"{NPM}/{encoded}", max_bytes=15_000_000)).data)
        budget.requests += 1
        readme = str(full.get("readme") or "")
        inspection.profile["released"] = (full.get("time") or {}).get(version or "")
    except FetchError as exc:
        inspection.skip(f"{NPM}/{encoded}", exc.code)
    _add(
        budget,
        inspection,
        ReadDocument(
            url=f"https://www.npmjs.com/package/{inspection.title}/v/{version or ''}",
            title=f"{inspection.title} {version or ''} — npm facts".strip(),
            filename=f"{inspection.title.replace('/', '_')}-npm-facts.md",
            category="markdown",
            data=_facts(
                f"{inspection.title} {version or ''}".strip(),
                [
                    ("Description", latest.get("description")),
                    ("Version", version),
                    ("Released", inspection.profile.get("released")),
                    ("Licence", inspection.license),
                    ("Homepage", latest.get("homepage")),
                    ("Repository", repo_url),
                    ("Entry points", inspection.profile["entry_points"]),
                    ("Dependencies", dependencies),
                    ("Keywords", inspection.profile["keywords"]),
                ],
            ),
            meta={"kind": "registry_facts"},
        ),
    )
    if readme.strip() and readme.strip() != "ERROR: No README data found!":
        _add(
            budget,
            inspection,
            ReadDocument(
                url=f"https://www.npmjs.com/package/{inspection.title}",
                title=f"{inspection.title} — README (npm)",
                filename=f"{inspection.title.replace('/', '_')}-README.md",
                category="markdown",
                data=readme.encode("utf-8")[: budget.limits.max_file_kb * 1024 * 4],
                meta={"kind": "readme"},
            ),
        )
    homepage = str(latest.get("homepage") or "")
    if homepage and "github.com" not in homepage and "npmjs.com" not in homepage:
        await _read_docs(fetcher, homepage, budget, inspection)
