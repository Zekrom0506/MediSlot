import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import rate_limiter as rate_limiter_module
from app.core.errors import RateLimitExceededError
from app.core.rate_limiter import RateLimiter
from tests.factories import auth_headers, make_doctor, make_slot, make_user


class FakeClock:
    """Lets a test move time forward without sleeping."""

    def __init__(self, start: float) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_blocks() -> None:
    clock = FakeClock(999_980)
    limiter = RateLimiter("unit", limit=3, window_seconds=60, clock=clock)

    for _attempt in range(3):
        limiter.hit("user-1")

    with pytest.raises(RateLimitExceededError) as error_info:
        limiter.hit("user-1")
    # 999_980 is 20 seconds into its 60 second window, so 40 seconds remain.
    assert error_info.value.headers == {"Retry-After": "40"}


def test_counts_each_identifier_separately() -> None:
    limiter = RateLimiter("unit", limit=1, clock=FakeClock(2_000_000))
    limiter.hit("first")
    limiter.hit("second")
    with pytest.raises(RateLimitExceededError):
        limiter.hit("first")


def test_new_window_resets_the_count() -> None:
    clock = FakeClock(3_000_000)
    limiter = RateLimiter("unit", limit=1, window_seconds=60, clock=clock)
    limiter.hit("user-1")

    clock.now += 60
    limiter.hit("user-1")


def test_fails_open_when_redis_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    broken_redis = redis.Redis(host="localhost", port=1, socket_connect_timeout=0.1)
    monkeypatch.setattr(rate_limiter_module, "get_redis", lambda: broken_redis)
    limiter = RateLimiter("unit", limit=1)

    limiter.hit("user-1")
    limiter.hit("user-1")


def test_sixth_booking_attempt_in_a_minute_gets_429(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    patient = make_user(db)
    slot = make_slot(db, doctor)

    status_codes = []
    for _attempt in range(6):
        response = client.post("/api/bookings", json={"slot_id": slot.id}, headers=auth_headers(patient))
        status_codes.append(response.status_code)

    assert status_codes == [201, 409, 409, 409, 409, 429]
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_eleventh_login_attempt_from_same_ip_gets_429(client: TestClient) -> None:
    status_codes = []
    for _attempt in range(11):
        response = client.post("/api/auth/login", json={"email": "who@example.com", "password": "guess"})
        status_codes.append(response.status_code)

    assert status_codes[:10] == [401] * 10
    assert status_codes[10] == 429
    assert "Retry-After" in response.headers
