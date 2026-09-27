from datetime import time

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.redis_client import get_redis
from app.core.timezones import local_to_utc
from app.services import cache_service
from tests.factories import auth_headers, future_date, make_doctor, make_slot_at, make_user


def slots_url(doctor_id: int, day) -> str:
    return f"/api/doctors/{doctor_id}/slots?date={day.isoformat()}"


def test_first_read_fills_cache_and_second_read_uses_it(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    day = future_date(2)
    slot = make_slot_at(db, doctor, local_to_utc(day, time(10, 0)))

    first = client.get(slots_url(doctor.id, day))
    assert get_redis().exists(cache_service.slots_cache_key(doctor.id, day)) == 1

    # Change the database behind the cache's back: the cached answer is still served.
    slot.status = "blocked"
    db.commit()
    second = client.get(slots_url(doctor.id, day))

    assert first.json() == second.json()
    assert get_redis().ttl(cache_service.slots_cache_key(doctor.id, day)) <= 60


def test_booking_clears_the_cached_day(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    day = future_date(2)
    slot = make_slot_at(db, doctor, local_to_utc(day, time(10, 0)))
    make_slot_at(db, doctor, local_to_utc(day, time(11, 0)))
    assert len(client.get(slots_url(doctor.id, day)).json()) == 2

    client.post("/api/bookings", json={"slot_id": slot.id}, headers=auth_headers(make_user(db)))

    assert get_redis().exists(cache_service.slots_cache_key(doctor.id, day)) == 0
    assert len(client.get(slots_url(doctor.id, day)).json()) == 1


def test_cancel_and_block_also_clear_the_cache(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    day = future_date(3)
    slot = make_slot_at(db, doctor, local_to_utc(day, time(10, 0)))
    other_slot = make_slot_at(db, doctor, local_to_utc(day, time(11, 0)))
    patient = make_user(db)
    booking_id = client.post(
        "/api/bookings", json={"slot_id": slot.id}, headers=auth_headers(patient)
    ).json()["id"]
    assert len(client.get(slots_url(doctor.id, day)).json()) == 1

    client.post(f"/api/bookings/{booking_id}/cancel", headers=auth_headers(patient))
    assert len(client.get(slots_url(doctor.id, day)).json()) == 2

    client.post(f"/api/doctor/slots/{other_slot.id}/block", headers=auth_headers(doctor.user))
    assert len(client.get(slots_url(doctor.id, day)).json()) == 1


def test_slots_still_served_when_redis_is_down(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    doctor = make_doctor(db)
    day = future_date(2)
    make_slot_at(db, doctor, local_to_utc(day, time(10, 0)))
    broken_redis = redis.Redis(host="localhost", port=1, socket_connect_timeout=0.1)
    monkeypatch.setattr(cache_service, "get_redis", lambda: broken_redis)

    response = client.get(slots_url(doctor.id, day))

    assert response.status_code == 200
    assert len(response.json()) == 1
    cache_service.invalidate_slot_day(doctor.id, local_to_utc(day, time(10, 0)))
    cache_service.invalidate_doctor(doctor.id)
