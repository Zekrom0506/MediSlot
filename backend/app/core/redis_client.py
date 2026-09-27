from functools import lru_cache

import redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    """One shared Redis client. It keeps its own connection pool and is thread-safe."""
    return redis.Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_timeout=2,
        socket_connect_timeout=2,
    )
