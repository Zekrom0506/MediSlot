"""Rules that stop one patient from abusing the calendar, and bookings at closed places."""

import threading
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Booking
from app.models.enums import BookingStatus
from tests.factories import auth_headers, make_doctor, make_slot, make_user


def book(client: TestClient, patient, slot_id: int):
    return client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_headers(patient))


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_cannot_book_at_a_deactivated_clinic_even_with_a_direct_request(
    client: TestClient, db: Session
) -> None:
    doctor = make_doctor(db)
    slot = make_slot(db, doctor)
    doctor.clinic.is_active = False
    db.commit()

    response = book(client, make_user(db), slot.id)

    assert response.status_code == 409
    assert error_code(response) == "SLOT_NOT_AVAILABLE"


def test_only_one_upcoming_appointment_per_doctor(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    patient = make_user(db)
    first_slot = make_slot(db, doctor, starts_in=timedelta(days=2))
    second_slot = make_slot(db, doctor, starts_in=timedelta(days=3))

    first = book(client, patient, first_slot.id)
    second = book(client, patient, second_slot.id)

    assert first.status_code == 201
    assert second.status_code == 409
    assert error_code(second) == "ALREADY_BOOKED_WITH_DOCTOR"

    # After cancelling, booking that doctor again is fine.
    client.post(f"/api/bookings/{first.json()['id']}/cancel", headers=auth_headers(patient))
    assert book(client, patient, second_slot.id).status_code == 201


def test_cannot_hold_two_appointments_at_the_same_time(client: TestClient, db: Session) -> None:
    patient = make_user(db)
    slot_a = make_slot(db, make_doctor(db), starts_in=timedelta(days=2))
    # Another doctor, starting 15 minutes into the first 30 minute appointment.
    slot_b = make_slot(db, make_doctor(db), starts_in=timedelta(days=2, minutes=15))
    slot_c = make_slot(db, make_doctor(db), starts_in=timedelta(days=2, minutes=30))

    assert book(client, patient, slot_a.id).status_code == 201
    overlapping = book(client, patient, slot_b.id)
    right_after = book(client, patient, slot_c.id)

    assert overlapping.status_code == 409
    assert error_code(overlapping) == "OVERLAPPING_BOOKING"
    assert right_after.status_code == 201


def test_limit_on_upcoming_appointments(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_upcoming_bookings_per_patient", 2)
    patient = make_user(db)
    slots = [make_slot(db, make_doctor(db), starts_in=timedelta(days=day)) for day in (1, 2, 3)]

    responses = [book(client, patient, slot.id) for slot in slots]

    assert [response.status_code for response in responses] == [201, 201, 409]
    assert error_code(responses[2]) == "TOO_MANY_BOOKINGS"


def test_reschedule_cannot_move_onto_another_appointment(client: TestClient, db: Session) -> None:
    patient = make_user(db)
    doctor = make_doctor(db)
    booking_id = book(client, patient, make_slot(db, doctor, starts_in=timedelta(days=2)).id).json()["id"]
    book(client, patient, make_slot(db, make_doctor(db), starts_in=timedelta(days=4)).id)
    clashing_slot = make_slot(db, doctor, starts_in=timedelta(days=4))

    response = client.post(
        f"/api/bookings/{booking_id}/reschedule",
        json={"new_slot_id": clashing_slot.id},
        headers=auth_headers(patient),
    )

    assert response.status_code == 409
    assert error_code(response) == "OVERLAPPING_BOOKING"


def test_parallel_requests_from_one_patient_cannot_beat_the_limits(db: Session, live_server_url: str) -> None:
    """Five requests for five slots of one doctor, sent at the same instant: only one wins.

    Without the lock on the patient's row, every request would see "no booking
    with this doctor yet" before any of them commits, and all five would succeed.
    """
    doctor = make_doctor(db)
    patient = make_user(db)
    slots = [make_slot(db, doctor, starts_in=timedelta(days=day)) for day in range(1, 6)]
    headers = auth_headers(patient)
    start_together = threading.Barrier(len(slots))
    status_codes: list[int] = []
    results_lock = threading.Lock()

    def try_to_book(slot_id: int) -> None:
        with httpx.Client(base_url=live_server_url, timeout=60) as http_client:
            start_together.wait()
            response = http_client.post("/api/bookings", json={"slot_id": slot_id}, headers=headers)
        with results_lock:
            status_codes.append(response.status_code)

    threads = [threading.Thread(target=try_to_book, args=(slot.id,)) for slot in slots]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(status_codes) == [201, 409, 409, 409, 409]
    db.expire_all()
    confirmed = db.scalar(
        select(func.count(Booking.id))
        .where(Booking.patient_id == patient.id)
        .where(Booking.status == BookingStatus.CONFIRMED.value)
    )
    assert confirmed == 1


def test_retries_answered_from_the_saved_response_are_not_rate_limited(
    client: TestClient, db: Session
) -> None:
    patient = make_user(db)
    slot = make_slot(db, make_doctor(db))
    headers = {**auth_headers(patient), "Idempotency-Key": "flaky-network-0001"}

    responses = [client.post("/api/bookings", json={"slot_id": slot.id}, headers=headers) for _ in range(10)]

    assert [response.status_code for response in responses] == [201] * 10
