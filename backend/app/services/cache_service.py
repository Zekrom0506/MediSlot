"""Cache-aside for a doctor's free slots on a given day.

Read:  look in Redis first; on a miss, read Postgres and store the result for 60s.
Write: whenever a slot changes, delete that day's cached list so the next read
       rebuilds it from the database.

The cache is only for *showing* slots. Booking always locks and checks the real
row in Postgres, so a stale cache can at worst show a slot that then returns 409.
"""

import json
import logging
from datetime import date, datetime
from typing import Any

import redis

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.core.timezones import to_local

logger = logging.getLogger(__name__)


def slots_cache_key(doctor_id: int, local_date: date) -> str:
    return f"slots:doctor:{doctor_id}:date:{local_date.isoformat()}"


def get_cached_slots(doctor_id: int, local_date: date) -> list[dict[str, Any]] | None:
    """Return the cached list, or None on a miss (or if Redis is down)."""
    try:
        cached_value = get_redis().get(slots_cache_key(doctor_id, local_date))
    except redis.RedisError:
        logger.warning("Slot cache read failed, falling back to the database")
        return None
    if cached_value is None:
        return None
    return json.loads(cached_value)


def store_cached_slots(doctor_id: int, local_date: date, slots: list[dict[str, Any]]) -> None:
    """Save the list with a short expiry, so even a missed invalidation heals itself."""
    try:
        get_redis().set(
            slots_cache_key(doctor_id, local_date),
            json.dumps(slots),
            ex=get_settings().slot_cache_seconds,
        )
    except redis.RedisError:
        logger.warning("Slot cache write failed")


def invalidate_slot_day(doctor_id: int, slot_start: datetime) -> None:
    """Forget the cached list for the clinic-local day this slot falls on."""
    local_date = to_local(slot_start).date()
    try:
        get_redis().delete(slots_cache_key(doctor_id, local_date))
    except redis.RedisError:
        logger.warning("Slot cache invalidation failed")


def invalidate_doctor(doctor_id: int) -> None:
    """Forget every cached day for a doctor (used after bulk changes like a new schedule)."""
    try:
        redis_client = get_redis()
        for key in redis_client.scan_iter(match=f"slots:doctor:{doctor_id}:date:*"):
            redis_client.delete(key)
    except redis.RedisError:
        logger.warning("Slot cache invalidation failed")
