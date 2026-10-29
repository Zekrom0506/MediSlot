from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Booking, Slot
from app.models.enums import BookingStatus, SlotStatus
from tests.factories import auth_headers, make_doctor, make_slot, make_user


def book(client: TestClient, patient, slot_id: int, reason: str | None = None):
    payload = {"slot_id": slot_id}
    if reason is not None:
        payload["reason_for_visit"] = reason
    return client.post("/api/bookings", json=payload, headers=auth_headers(patient))


def test_patient_books_a_free_slot(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db, full_name="Dr. Heart")
    slot = make_slot(db, doctor)
    patient = make_user(db)

    response = book(client, patient, slot.id, "Chest pain on exercise")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["reason_for_visit"] == "Chest pain on exercise"
    assert body["doctor"]["full_name"] == "Dr. Heart"
    assert body["slot"]["status"] == "booked"
    db.expire_all()
    assert db.get(Slot, slot.id).status == SlotStatus.BOOKED.value


def test_booking_a_taken_slot_returns_friendly_409(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    book(client, make_user(db), slot.id)

    response = book(client, make_user(db), slot.id)

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "SLOT_ALREADY_BOOKED",
            "message": "Sorry, this slot was just booked. Please choose another slot.",
        }
    }


def test_cannot_book_blocked_past_or_missing_slots(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    patient = make_user(db)
    blocked = make_slot(db, doctor, status=SlotStatus.BLOCKED)
    past = make_slot(db, doctor, starts_in=timedelta(hours=-1))

    assert book(client, patient, blocked.id).json()["error"]["code"] == "SLOT_NOT_AVAILABLE"
    assert book(client, patient, past.id).json()["error"]["code"] == "SLOT_IN_PAST"
    assert book(client, patient, 999).status_code == 404


def test_cannot_book_inactive_doctor(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    slot = make_slot(db, doctor)
    doctor.is_active = False
    db.commit()

    response = book(client, make_user(db), slot.id)
    assert response.status_code == 409


def test_only_patients_can_book(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    slot = make_slot(db, doctor)

    assert client.post("/api/bookings", json={"slot_id": slot.id}).status_code == 401
    assert book(client, doctor.user, slot.id).status_code == 403


def test_reason_for_visit_is_limited_to_500_characters(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    response = book(client, make_user(db), slot.id, "x" * 501)
    assert response.status_code == 422
    assert "reason_for_visit" in response.json()["error"]["message"]


def test_cancel_frees_the_slot_for_someone_else(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    first_patient = make_user(db)
    booking_id = book(client, first_patient, slot.id).json()["id"]

    cancel = client.post(f"/api/bookings/{booking_id}/cancel", headers=auth_headers(first_patient))
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert cancel.json()["cancelled_at"] is not None

    second_attempt = book(client, make_user(db), slot.id)
    assert second_attempt.status_code == 201


def test_cannot_cancel_within_two_hours(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db), starts_in=timedelta(hours=1))
    patient = make_user(db)
    booking_id = book(client, patient, slot.id).json()["id"]

    response = client.post(f"/api/bookings/{booking_id}/cancel", headers=auth_headers(patient))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CANCELLATION_WINDOW_CLOSED"
    db.expire_all()
    assert db.get(Booking, booking_id).status == BookingStatus.CONFIRMED.value


def test_cannot_cancel_someone_elses_booking_or_twice(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    owner = make_user(db)
    stranger = make_user(db)
    booking_id = book(client, owner, slot.id).json()["id"]

    as_stranger = client.post(f"/api/bookings/{booking_id}/cancel", headers=auth_headers(stranger))
    assert as_stranger.status_code == 403

    client.post(f"/api/bookings/{booking_id}/cancel", headers=auth_headers(owner))
    second_cancel = client.post(f"/api/bookings/{booking_id}/cancel", headers=auth_headers(owner))
    assert second_cancel.status_code == 409

    missing = client.post("/api/bookings/999/cancel", headers=auth_headers(owner))
    assert missing.status_code == 404


def test_upcoming_and_past_lists(client: TestClient, db: Session) -> None:
    # Different doctors: a patient can only have one upcoming visit per doctor.
    doctor = make_doctor(db)
    patient = make_user(db)
    later_slot = make_slot(db, make_doctor(db), starts_in=timedelta(days=3))
    sooner_slot = make_slot(db, make_doctor(db), starts_in=timedelta(days=1))
    cancelled_slot = make_slot(db, make_doctor(db), starts_in=timedelta(days=2))
    old_slot = make_slot(db, doctor, starts_in=timedelta(days=-2), status=SlotStatus.BOOKED)
    db.add(Booking(patient_id=patient.id, slot_id=old_slot.id, status=BookingStatus.COMPLETED.value))
    db.commit()

    later_id = book(client, patient, later_slot.id).json()["id"]
    sooner_id = book(client, patient, sooner_slot.id).json()["id"]
    cancelled_id = book(client, patient, cancelled_slot.id).json()["id"]
    client.post(f"/api/bookings/{cancelled_id}/cancel", headers=auth_headers(patient))

    upcoming = client.get("/api/bookings/me?scope=upcoming", headers=auth_headers(patient)).json()
    past = client.get("/api/bookings/me?scope=past", headers=auth_headers(patient)).json()

    assert [booking["id"] for booking in upcoming] == [sooner_id, later_id]
    assert len(past) == 2
    assert {booking["status"] for booking in past} == {"cancelled", "completed"}


def test_get_single_booking_checks_owner(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    owner = make_user(db)
    booking_id = book(client, owner, slot.id).json()["id"]

    assert client.get(f"/api/bookings/{booking_id}", headers=auth_headers(owner)).status_code == 200
    assert client.get(f"/api/bookings/{booking_id}", headers=auth_headers(make_user(db))).status_code == 403
    assert client.get("/api/bookings/999", headers=auth_headers(owner)).status_code == 404


def test_partial_unique_index_blocks_second_confirmed_booking(db: Session) -> None:
    """The database itself refuses two confirmed bookings for one slot."""
    slot = make_slot(db, make_doctor(db))
    first_patient = make_user(db)
    second_patient = make_user(db)
    db.add(Booking(patient_id=first_patient.id, slot_id=slot.id, status="confirmed"))
    db.commit()

    db.add(Booking(patient_id=second_patient.id, slot_id=slot.id, status="cancelled"))
    db.commit()

    db.add(Booking(patient_id=second_patient.id, slot_id=slot.id, status="confirmed"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    confirmed_count = db.scalar(
        select(func.count(Booking.id)).where(Booking.slot_id == slot.id).where(Booking.status == "confirmed")
    )
    assert confirmed_count == 1


def test_index_violation_is_turned_into_409(client: TestClient, db: Session) -> None:
    """Simulate a code path that forgot to update the slot status: the index still saves us."""
    slot = make_slot(db, make_doctor(db))
    db.add(Booking(patient_id=make_user(db).id, slot_id=slot.id, status="confirmed"))
    db.commit()

    response = book(client, make_user(db), slot.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SLOT_ALREADY_BOOKED"
