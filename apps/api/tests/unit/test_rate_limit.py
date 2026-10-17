import pytest

from ezo_api.security.rate_limit import RateLimitExceededError, SlidingWindowRateLimiter


def test_sliding_window() -> None:
    limiter = SlidingWindowRateLimiter(window_seconds=60)
    limiter.check("k", 2, now=0)
    limiter.check("k", 2, now=1)
    with pytest.raises(RateLimitExceededError) as info:
        limiter.check("k", 2, now=2)
    assert info.value.retry_after_seconds >= 1
    limiter.check("k", 2, now=61)  # first hit has left the window
    limiter.check("other", 2, now=2)  # keys are independent
