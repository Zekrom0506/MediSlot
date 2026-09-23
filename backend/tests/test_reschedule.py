from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, Slot
from app.models.enums import BookingStatus, SlotStatus
from tests.factories import auth_headers, make_doctor, make_slot, make_user


def confirmed_bookings_for(db: Session, patient_id: int) -> int:
    db.expire_all()
    return db.scalar(
        select(func.count(Booking.id))
        .where(Booking.patient_id == patient_id)
        .where(Booking.status == BookingStatus.CONFIRMED.value)
    )


def book(client: TestClient, patient, slot_id: int) -> int:
    response = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_headers(patient))
    assert response.status_code == 201
    return response.json()["id"]


def reschedule(client: TestClient, patient, booking_id: int, new_slot_id: int):
    return client.post(
        f"/api/bookings/{booking_id}/reschedule",
        json={"new_slot_id": new_slot_id},
        headers=auth_headers(patient),
    )


def test_reschedule_moves_booking_and_frees_old_slot(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    old_slot = make_slot(db, doctor, starts_in=timedelta(days=1))
    new_slot = make_slot(db, doctor, starts_in=timedelta(days=2))
    patient = make_user(db)
    booking_id = book(client, patient, old_slot.id)

    response = reschedule(client, patient, booking_id, new_slot.id)

    assert response.status_code == 200
    assert response.json()["slot"]["id"] == new_slot.id
    assert response.json()["id"] != booking_id
    assert confirmed_bookings_for(db, patient.id) == 1
    assert db.get(Booking, booking_id).status == BookingStatus.CANCELLED.value
    assert db.get(Slot, old_slot.id).status == SlotStatus.AVAILABLE.value
    assert db.get(Slot, new_slot.id).status == SlotStatus.BOOKED.value


def test_failed_reschedule_keeps_the_original_booking(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    old_slot = make_slot(db, doctor, starts_in=timedelta(days=1))
    taken_slot = make_slot(db, doctor, starts_in=timedelta(days=2))
    patient = make_user(db)
    booking_id = book(client, patient, old_slot.id)
    book(client, make_user(db), taken_slot.id)

    response = reschedule(client, patient, booking_id, taken_slot.id)

    assert response.status_code == 409
    assert confirmed_bookings_for(db, patient.id) == 1
    assert db.get(Booking, booking_id).status == BookingStatus.CONFIRMED.value
    assert db.get(Slot, old_slot.id).status == SlotStatus.BOOKED.value


def test_reschedule_rules(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    other_doctor = make_doctor(db, clinic=doctor.clinic)
    soon_slot = make_slot(db, doctor, starts_in=timedelta(hours=1))
    later_slot = make_slot(db, doctor, starts_in=timedelta(days=2))
    other_doctor_slot = make_slot(db, other_doctor, starts_in=timedelta(days=2))
    patient = make_user(db)
    soon_booking_id = book(client, patient, soon_slot.id)

    too_late = reschedule(client, patient, soon_booking_id, later_slot.id)
    assert too_late.json()["error"]["code"] == "CANCELLATION_WINDOW_CLOSED"

    other_doctor_attempt = reschedule(client, patient, soon_booking_id, other_doctor_slot.id)
    assert other_doctor_attempt.json()["error"]["code"] == "DIFFERENT_DOCTOR"

    same_slot = reschedule(client, patient, soon_booking_id, soon_slot.id)
    assert same_slot.json()["error"]["code"] == "SAME_SLOT"

    not_owner = reschedule(client, make_user(db), soon_booking_id, later_slot.id)
    assert not_owner.status_code == 403

    missing_slot = reschedule(client, patient, soon_booking_id, 999)
    assert missing_slot.status_code == 404

    assert confirmed_bookings_for(db, patient.id) == 1


def test_patient_always_has_exactly_one_booking_across_many_reschedules(
    client: TestClient, db: Session
) -> None:
    doctor = make_doctor(db)
    slots = []
    for day in range(1, 6):
        slots.append(make_slot(db, doctor, starts_in=timedelta(days=day)))
    patient = make_user(db)
    booking_id = book(client, patient, slots[0].id)

    for next_slot in slots[1:]:
        response = reschedule(client, patient, booking_id, next_slot.id)
        assert response.status_code == 200
        booking_id = response.json()["id"]
        assert confirmed_bookings_for(db, patient.id) == 1

    booked_slots = db.scalar(
        select(func.count(Slot.id)).where(Slot.doctor_id == doctor.id).where(Slot.status == "booked")
    )
    assert booked_slots == 1
