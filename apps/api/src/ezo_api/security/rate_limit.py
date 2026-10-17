"""In-memory sliding-window rate limiter.

Good for a single API process (the Milestone 1 deployment). When EZO runs
several API workers, swap this for a Redis-backed limiter with the same
`check` method.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimitExceededError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Rate limit exceeded; retry after {retry_after_seconds}s")


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, now: float | None = None) -> None:
        """Record a hit for `key`; raise if more than `limit` hits in the window."""
        if limit <= 0:
            return
        current = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and current - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= limit:
            retry_after = max(1, int(self.window - (current - hits[0])) + 1)
            raise RateLimitExceededError(retry_after)
        hits.append(current)
        if len(self._hits) > 10_000:
            self._evict(current)

    def _evict(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
            del self._hits[key]
