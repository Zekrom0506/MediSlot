import threading
import uuid
from datetime import timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.timezones import now_utc
from app.models import Booking, IdempotencyKey
from app.services import idempotency_service
from tests.factories import auth_headers, make_doctor, make_slot, make_user


def count_bookings(db: Session) -> int:
    return db.scalar(select(func.count(Booking.id)))


def headers_with_key(patient, key: str) -> dict[str, str]:
    headers = auth_headers(patient)
    headers["Idempotency-Key"] = key
    return headers


def test_same_key_five_times_creates_one_booking(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    patient = make_user(db)
    key = str(uuid.uuid4())

    responses = []
    for _attempt in range(5):
        responses.append(
            client.post("/api/bookings", json={"slot_id": slot.id}, headers=headers_with_key(patient, key))
        )

    assert [response.status_code for response in responses] == [201, 201, 201, 201, 201]
    first_body = responses[0].json()
    for response in responses[1:]:
        assert response.json() == first_body
        assert response.headers["Idempotent-Replayed"] == "true"
    assert "Idempotent-Replayed" not in responses[0].headers
    assert count_bookings(db) == 1


def test_same_key_sent_in_parallel_creates_one_booking(db: Session, live_server_url: str) -> None:
    slot = make_slot(db, make_doctor(db))
    patient = make_user(db)
    headers = headers_with_key(patient, str(uuid.uuid4()))
    start_together = threading.Barrier(5)
    results = []
    results_lock = threading.Lock()

    def send_request() -> None:
        with httpx.Client(base_url=live_server_url, timeout=30) as http_client:
            start_together.wait()
            response = http_client.post("/api/bookings", json={"slot_id": slot.id}, headers=headers)
        with results_lock:
            results.append(response)

    threads = [threading.Thread(target=send_request) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [response.status_code for response in results] == [201] * 5
    booking_ids = {response.json()["id"] for response in results}
    assert len(booking_ids) == 1
    db.expire_all()
    assert count_bookings(db) == 1


def test_different_keys_are_different_attempts(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    patient = make_user(db)

    first = client.post(
        "/api/bookings", json={"slot_id": slot.id}, headers=headers_with_key(patient, "key-aaaa-1")
    )
    second = client.post(
        "/api/bookings", json={"slot_id": slot.id}, headers=headers_with_key(patient, "key-bbbb-2")
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_key_cannot_be_reused_for_other_slot_or_user(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    first_slot = make_slot(db, doctor, starts_in=timedelta(days=1))
    second_slot = make_slot(db, doctor, starts_in=timedelta(days=2))
    patient = make_user(db)
    key = "reused-key-123"
    client.post("/api/bookings", json={"slot_id": first_slot.id}, headers=headers_with_key(patient, key))

    other_slot = client.post(
        "/api/bookings", json={"slot_id": second_slot.id}, headers=headers_with_key(patient, key)
    )
    other_user = client.post(
        "/api/bookings", json={"slot_id": first_slot.id}, headers=headers_with_key(make_user(db), key)
    )

    assert other_slot.status_code == 422
    assert other_slot.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert other_user.status_code == 422
    assert count_bookings(db) == 1


def test_failed_attempt_does_not_store_key(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    client.post("/api/bookings", json={"slot_id": slot.id}, headers=auth_headers(make_user(db)))
    patient = make_user(db)

    response = client.post(
        "/api/bookings", json={"slot_id": slot.id}, headers=headers_with_key(patient, "lost-race-1")
    )

    assert response.status_code == 409
    assert db.scalar(select(func.count(IdempotencyKey.id))) == 0


def test_invalid_key_format_is_rejected(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    response = client.post(
        "/api/bookings", json={"slot_id": slot.id}, headers=headers_with_key(make_user(db), "bad key!")
    )
    assert response.status_code == 422


def test_delete_expired_keys_only_removes_old_ones(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    patient = make_user(db)
    old_slot = make_slot(db, doctor, starts_in=timedelta(days=1))
    new_slot = make_slot(db, doctor, starts_in=timedelta(days=2))
    client.post(
        "/api/bookings", json={"slot_id": old_slot.id}, headers=headers_with_key(patient, "old-key-0001")
    )
    client.post(
        "/api/bookings", json={"slot_id": new_slot.id}, headers=headers_with_key(patient, "new-key-0002")
    )
    db.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.key == "old-key-0001")
        .values(created_at=now_utc() - timedelta(hours=25))
    )
    db.commit()

    deleted = idempotency_service.delete_expired_keys(db)

    assert deleted == 1
    remaining = list(db.scalars(select(IdempotencyKey.key)))
    assert remaining == ["new-key-0002"]
