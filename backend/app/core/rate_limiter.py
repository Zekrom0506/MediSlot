"""A small fixed-window rate limiter on top of Redis.

Time is cut into windows of `window_seconds` (e.g. 12:00:00-12:00:59). Each
window has its own counter key in Redis, e.g. "ratelimit:login:1.2.3.4:28512340".
Every request increments the counter; once it goes over the limit, requests are
rejected until the next window starts. The key expires by itself afterwards.

Weakness: a burst at the end of one window plus a burst at the start of the next
can let through up to 2x the limit in a short time. A sliding window (for example
a sorted set of request timestamps) avoids that, at the cost of more memory.
"""

import logging
import time
from collections.abc import Callable

import redis

from app.core.config import get_settings
from app.core.errors import RateLimitExceededError
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


class RateLimiter:
    """Allow at most `limit` hits per identifier in each window."""

    def __init__(
        self,
        name: str,
        limit: int,
        window_seconds: int = 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock

    def hit(self, identifier: str) -> None:
        """Count one request. Raises RateLimitExceededError when over the limit."""
        if not get_settings().rate_limit_enabled:
            return

        current_time = int(self.clock())
        window_number = current_time // self.window_seconds
        key = f"ratelimit:{self.name}:{identifier}:{window_number}"

        try:
            # INCR and EXPIRE are sent together in one round trip. INCR is atomic,
            # so two simultaneous requests can never read the same count.
            pipeline = get_redis().pipeline()
            pipeline.incr(key)
            pipeline.expire(key, self.window_seconds)
            request_count, _ = pipeline.execute()
        except redis.RedisError:
            # Fail open: if Redis is down we would rather serve requests than block everyone.
            logger.warning("Rate limiter unavailable, allowing request", extra={"limiter": self.name})
            return

        if request_count > self.limit:
            seconds_left_in_window = self.window_seconds - (current_time % self.window_seconds)
            raise RateLimitExceededError(
                "RATE_LIMITED",
                "Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(seconds_left_in_window)},
            )


def booking_limiter() -> RateLimiter:
    return RateLimiter("booking", get_settings().booking_rate_limit_per_minute)


def login_limiter() -> RateLimiter:
    return RateLimiter("login", get_settings().login_rate_limit_per_minute)
