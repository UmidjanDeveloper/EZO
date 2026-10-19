"""Reading a documentation website: breadth-first, inside one site and folder.

Rules:
- Only the start page's host and its folder (https://docs.x.org/en/latest/… stays under
  /en/latest/). No other hosts, no parent folders.
- robots.txt is respected for every page (SafeFetcher), and its Crawl-delay is honoured.
- One request at a time per host with a minimum interval (politeness).
- Only HTML, plain text, Markdown and PDF (SafeFetcher's content allow-list); links to
  archives, images, executables and similar files are never requested.
- Hard budgets: pages, depth, total size, time. When one is reached the reading stops and
  the reason is recorded.
Pages are data: links are followed only by these rules, never because a page says so.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from ezo_api.knowledge.fetch import FetchError, SafeFetcher
from ezo_api.learning.base import Budget, Inspection, ReadDocument
from ezo_api.learning.targets import canonical_url

SKIP_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tif", ".tiff",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".whl", ".egg", ".jar",
    ".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".iso", ".bin", ".so", ".dll",
    ".mp3", ".mp4", ".avi", ".mov", ".webm", ".wav", ".ogg", ".woff", ".woff2", ".ttf",
    ".eot", ".css", ".js", ".mjs", ".map", ".json", ".xml", ".rss", ".atom",
    ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".epub",
)  # fmt: skip
MAX_LINKS_PER_PAGE = 300
MAX_QUEUE = 2_000


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.title = ""
        self._in_title = False
        self.base: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href") and len(self.links) < MAX_LINKS_PER_PAGE:
            self.links.append(values["href"] or "")
        elif tag == "base" and values.get("href") and self.base is None:
            self.base = values["href"]
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and len(self.title) < 300:
            self.title += data


def page_links(html: str, page_url: str) -> tuple[str, list[str]]:
    """The page title and its absolute link targets (fragments removed)."""
    parser = _Links()
    with contextlib.suppress(Exception):  # malformed HTML: keep what was parsed
        parser.feed(html)
    base = urljoin(page_url, parser.base) if parser.base else page_url
    links = []
    for href in parser.links:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:", "data:")):
            continue
        absolute = urljoin(base, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            continue
        links.append(urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, "")))
    return " ".join(parser.title.split()), links


def scope_of(url: str) -> tuple[str, str]:
    """(host, folder prefix) a crawl may not leave."""
    parts = urlsplit(url)
    path = parts.path or "/"
    folder = path if path.endswith("/") else path.rsplit("/", 1)[0] + "/"
    return (parts.netloc.lower(), folder)


def in_scope(url: str, scope: tuple[str, str]) -> bool:
    parts = urlsplit(url)
    if parts.netloc.lower() != scope[0]:
        return False
    path = parts.path or "/"
    if not path.startswith(scope[1]):
        return False
    return not path.lower().endswith(SKIP_EXTENSIONS)


class Pacer:
    """At most one request per host per interval."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._last: dict[str, float] = {}

    async def wait(self, host: str, delay: float | None = None) -> None:
        interval = max(self.interval, min(delay or 0.0, 30.0))
        last = self._last.get(host)
        if last is not None:
            remaining = interval - (time.monotonic() - last)
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last[host] = time.monotonic()


def _category(content_type: str) -> str:
    if content_type == "application/pdf":
        return "pdf"
    if content_type in ("text/html", "application/xhtml+xml"):
        return "html"
    if content_type == "text/markdown":
        return "markdown"
    return "text"


async def crawl(
    fetcher: SafeFetcher, start_url: str, budget: Budget, inspection: Inspection
) -> None:
    """Read the site into `inspection.documents` within the budget."""
    start = canonical_url(start_url)
    scope = scope_of(start)
    pacer = Pacer(budget.limits.min_interval_seconds)
    queue: list[tuple[str, int]] = [(start, 0)]
    seen = {start}
    while queue:
        if reason := budget.over():
            inspection.stopped = reason
            break
        url, depth = queue.pop(0)
        host = urlsplit(url).netloc
        try:
            if not await fetcher.allowed_by_robots(url):
                inspection.skip(url, "robots")
                continue
            await pacer.wait(host, fetcher.crawl_delay(url))
            budget.requests += 1
            remaining = int(budget.limits.max_total_mb * 1024 * 1024) - budget.bytes
            page = await fetcher.fetch(url, respect_robots=False, max_bytes=max(1, remaining))
        except FetchError as exc:
            inspection.skip(url, exc.code)
            if url == start:
                inspection.errors.append(exc.message)
            continue
        final = canonical_url(page.final_url)
        if final != url and not in_scope(final, scope):
            inspection.skip(url, "redirect_out_of_scope")
            continue
        seen.add(final)
        category = _category(page.content_type)
        title = ""
        if category == "html":
            html = page.data.decode("utf-8", errors="replace")
            title, links = page_links(html, final)
            if depth < budget.limits.max_depth:
                for link in links:
                    link = canonical_url(link)
                    if link not in seen and in_scope(link, scope) and len(queue) < MAX_QUEUE:
                        seen.add(link)
                        queue.append((link, depth + 1))
        budget.documents += 1
        budget.bytes += len(page.data)
        name = urlsplit(final).path.rstrip("/").rsplit("/", 1)[-1] or "index"
        inspection.documents.append(
            ReadDocument(
                url=final,
                title=title or name,
                filename=name[:150],
                category=category,
                data=page.data,
                meta={"depth": depth, "fetched_at": page.fetched_at},
            )
        )
    if queue and inspection.stopped is None and budget.over():
        inspection.stopped = budget.over()
    inspection.profile["pages_found"] = len(seen)
