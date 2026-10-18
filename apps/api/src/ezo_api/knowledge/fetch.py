"""Safe HTTP fetching for user-supplied and model-chosen URLs.

Protections (SSRF): only http/https, no credentials in URLs, every hostname
(including each redirect hop) must resolve to public IP addresses, limited
redirects, timeouts, a response size cap and an allow-list of content types.
robots.txt is respected for automated fetches.

Residual risk: DNS could change between our check and the connection
(DNS rebinding). Keep EZO_FETCH_ALLOW_PRIVATE_NETWORKS=false on servers.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "EZO/0.2 (personal AI assistant; respects robots.txt)"
MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(15.0, connect=8.0)
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "application/pdf",
)


class FetchError(Exception):
    """Fetching failed. `message` is safe to show to the user."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status = status
        """HTTP status for `http` errors (lets callers tell 403 from 429 from 503)."""
        self.retry_after = retry_after
        """Seconds from a `Retry-After` header, when the server sent one."""
        super().__init__(message)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        return None  # HTTP-date form: treated as "unknown"


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    final_url: str
    content_type: str
    data: bytes
    fetched_at: float


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip in ipaddress.ip_network("100.64.0.0/10")
    )


def validate_url(url: str) -> tuple[str, int]:
    """Check URL shape; return (host, port)."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise FetchError("bad_url", "Only http:// and https:// links can be opened.")
    if not parts.hostname:
        raise FetchError("bad_url", "The link has no website address.")
    if parts.username or parts.password:
        raise FetchError("bad_url", "Links with a username or password are not allowed.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.hostname, port


class SafeFetcher:
    def __init__(
        self,
        allow_private_networks: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Callable[[str, int], Awaitable[list[str]]] | None = None,
    ) -> None:
        self.allow_private = allow_private_networks
        self._transport = transport
        self._resolve = resolver or self._default_resolve
        self._robots: dict[str, tuple[float, RobotFileParser | None]] = {}

    @staticmethod
    async def _default_resolve(host: str, port: int) -> list[str]:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
        return sorted({str(info[4][0]) for info in infos})

    async def check_host(self, url: str) -> None:
        host, port = validate_url(url)
        if self.allow_private:
            return
        try:
            literal = ipaddress.ip_address(host)
            addresses = [str(literal)]
        except ValueError:
            try:
                addresses = await self._resolve(host, port)
            except OSError as exc:
                raise FetchError("dns", f"The website {host} could not be found.") from exc
        if not addresses or not all(_is_public(address) for address in addresses):
            raise FetchError("blocked", "This address points to a private network and is blocked.")

    def _client(self, accept: tuple[str, ...] = ALLOWED_CONTENT_TYPES) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": ", ".join(accept)},
        )

    async def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None or time.monotonic() - cached[0] > 3600:
            parser: RobotFileParser | None = None
            try:
                page = await self._get(origin + "/robots.txt", max_bytes=512_000)
                robots = RobotFileParser()
                robots.parse(page.data.decode("utf-8", errors="replace").splitlines())
                parser = robots
            except FetchError:
                pass  # no robots.txt (or unreachable): allowed
            self._robots[origin] = (time.monotonic(), parser)
            cached = self._robots[origin]
        parser = cached[1]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    async def fetch(self, url: str, respect_robots: bool = True) -> FetchedPage:
        if respect_robots and not await self.allowed_by_robots(url):
            raise FetchError("robots", "The website does not allow automated access to this page.")
        return await self._get(url, MAX_BYTES)

    async def fetch_json(self, url: str, max_bytes: int = 2_000_000) -> FetchedPage:
        """A JSON API response (same SSRF and size protections; only application/json)."""
        return await self._get(url, max_bytes, accept=("application/json",))

    async def _get(
        self, url: str, max_bytes: int, accept: tuple[str, ...] = ALLOWED_CONTENT_TYPES
    ) -> FetchedPage:
        current = url
        async with self._client(accept) as client:
            for _ in range(MAX_REDIRECTS + 1):
                await self.check_host(current)
                try:
                    async with client.stream("GET", current) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise FetchError("http", "The website sent a broken redirect.")
                            current = urljoin(current, location)
                            continue
                        if response.status_code >= 400:
                            raise FetchError(
                                "http",
                                f"The website answered with error {response.status_code}.",
                                status=response.status_code,
                                retry_after=_retry_after(response.headers.get("retry-after")),
                            )
                        content_type = response.headers.get("content-type", "").split(";")[0]
                        content_type = content_type.strip().lower()
                        if content_type and not content_type.startswith(accept):
                            raise FetchError(
                                "content_type", f"Unsupported content type: {content_type}."
                            )
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise FetchError("too_large", "The page is too large to read.")
                            chunks.append(chunk)
                        return FetchedPage(
                            url=url,
                            final_url=str(current),
                            content_type=content_type or "text/html",
                            data=b"".join(chunks),
                            fetched_at=time.time(),
                        )
                except httpx.TimeoutException as exc:
                    raise FetchError("timeout", "The website took too long to answer.") from exc
                except httpx.HTTPError as exc:
                    raise FetchError(
                        "network", f"Could not open the page ({type(exc).__name__})."
                    ) from exc
        raise FetchError("redirects", "Too many redirects.")
