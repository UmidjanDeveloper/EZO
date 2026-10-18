"""Polite, rule-following HTTP for official sources.

On top of SafeFetcher (SSRF protection, size and type limits):
- only the connector's allow-listed hosts;
- robots.txt is obeyed; 404/410 means "no rules", but 401/403 means access is
  refused and 5xx/network errors mean EZO does not know the rules, so it does not
  fetch (fail closed, RFC 9309 §2.3.1.4);
- at least `min_interval` seconds between two requests to the same source and a
  request budget per run;
- 401/403/451 → AccessRestrictedError (never retried, never worked around);
- 429 → RateLimitedError with the server's Retry-After.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import anyio

from ezo_api.knowledge.fetch import USER_AGENT, FetchedPage, FetchError, SafeFetcher
from ezo_api.official.base import (
    AccessRestrictedError,
    BudgetExhaustedError,
    RateLimitedError,
    RobotsUnavailableError,
    SourcePolicy,
    TemporaryFetchError,
    UnsupportedSourceError,
)

Sleep = Callable[[float], Awaitable[None]]
_REFUSED = (401, 403, 451)


class OfficialHttpClient:
    def __init__(
        self,
        fetcher: SafeFetcher,
        policy: SourcePolicy,
        *,
        min_interval: float,
        max_requests: int,
        sleep: Sleep | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.fetcher = fetcher
        self.policy = policy
        self.min_interval = max(min_interval, policy.min_interval_seconds)
        self.max_requests = max_requests
        self.requests_made = 0
        self._sleep = sleep or anyio.sleep
        self._clock = clock
        self._last: float | None = None
        self._robots: dict[str, RobotFileParser | None] = {}

    def _check_host(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme != "https" or (parts.hostname or "") not in self.policy.allowed_hosts:
            raise UnsupportedSourceError(f"{url} is not an allowed address for {self.policy.name}.")

    async def _pace(self) -> None:
        if self.requests_made >= self.max_requests:
            raise BudgetExhaustedError(
                f"The request budget for this run ({self.max_requests}) is used up."
            )
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                await self._sleep(wait)
        self._last = self._clock()
        self.requests_made += 1

    async def _raw(self, url: str) -> FetchedPage:
        await self._pace()
        try:
            return await self.fetcher.fetch(url, respect_robots=False)  # robots handled here
        except FetchError as exc:
            if exc.status in _REFUSED:
                raise AccessRestrictedError(
                    f"{self.policy.name} refused access (HTTP {exc.status}). EZO does not "
                    "work around access restrictions."
                ) from exc
            if exc.status == 429:
                raise RateLimitedError(
                    f"{self.policy.name} asked EZO to slow down (HTTP 429).", exc.retry_after
                ) from exc
            if exc.status in (404, 410):
                raise
            raise TemporaryFetchError(exc.message) from exc

    async def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        try:
            page = await self._raw(origin + "/robots.txt")
        except FetchError as exc:  # 404 / 410: the site publishes no rules
            parser = None
            if exc.status not in (404, 410):
                raise RobotsUnavailableError(
                    f"robots.txt of {parts.hostname} could not be read; EZO does not fetch "
                    "without knowing the site's rules."
                ) from exc
        except AccessRestrictedError:
            raise
        except TemporaryFetchError as exc:
            raise RobotsUnavailableError(
                f"robots.txt of {parts.hostname} could not be read ({exc.message}); EZO does "
                "not fetch without knowing the site's rules."
            ) from exc
        else:
            parser = RobotFileParser()
            parser.parse(page.data.decode("utf-8", errors="replace").splitlines())
            delay = parser.crawl_delay(USER_AGENT)
            if delay:
                self.min_interval = max(self.min_interval, float(delay))
        self._robots[origin] = parser
        return parser

    async def get(self, url: str) -> FetchedPage:
        self._check_host(url)
        robots = await self._robots_for(url)
        if robots is not None and not robots.can_fetch(USER_AGENT, url):
            raise AccessRestrictedError(
                f"robots.txt of {self.policy.name} does not allow automated access to this page."
            )
        try:
            return await self._raw(url)
        except FetchError as exc:  # 404 / 410 for the document itself
            raise TemporaryFetchError(
                f"{self.policy.name} has no document at this address (HTTP {exc.status})."
            ) from exc
