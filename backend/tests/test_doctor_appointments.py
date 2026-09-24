from datetime import time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.timezones import local_to_utc, today_local
from app.models import Booking
from app.models.enums import BookingStatus, SlotStatus
from tests.factories import auth_headers, make_doctor, make_slot, make_slot_at, make_user


def add_booking(db: Session, slot, patient, status: BookingStatus = BookingStatus.CONFIRMED) -> Booking:
    booking = Booking(patient_id=patient.id, slot_id=slot.id, status=status.value, reason_for_visit="Checkup")
    db.add(booking)
    db.commit()
    return booking


def test_upcoming_appointments_show_patient_details(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    patient = make_user(db, full_name="Neha Patient")
    future_slot = make_slot(db, doctor, starts_in=timedelta(days=1), status=SlotStatus.BOOKED)
    add_booking(db, future_slot, patient)

    response = client.get("/api/doctor/appointments?scope=upcoming", headers=auth_headers(doctor.user))

    assert response.status_code == 200
    appointment = response.json()[0]
    assert appointment["patient"]["full_name"] == "Neha Patient"
    assert appointment["reason_for_visit"] == "Checkup"


def test_today_lists_only_todays_non_cancelled_appointments(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    patient = make_user(db)
    start_of_today = local_to_utc(today_local(), time(0, 1))
    today_slot = make_slot_at(db, doctor, start_of_today, status=SlotStatus.BOOKED)
    cancelled_slot = make_slot_at(db, doctor, start_of_today + timedelta(minutes=30))
    tomorrow_slot = make_slot_at(db, doctor, start_of_today + timedelta(days=1), status=SlotStatus.BOOKED)
    today_booking = add_booking(db, today_slot, patient)
    add_booking(db, cancelled_slot, patient, BookingStatus.CANCELLED)
    add_booking(db, tomorrow_slot, patient)

    response = client.get("/api/doctor/appointments?scope=today", headers=auth_headers(doctor.user))

    assert [appointment["id"] for appointment in response.json()] == [today_booking.id]


def test_doctor_marks_started_appointment_completed(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    past_slot = make_slot(db, doctor, starts_in=timedelta(hours=-1), status=SlotStatus.BOOKED)
    booking = add_booking(db, past_slot, make_user(db))

    response = client.patch(
        f"/api/doctor/appointments/{booking.id}",
        json={"status": "completed"},
        headers=auth_headers(doctor.user),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    again = client.patch(
        f"/api/doctor/appointments/{booking.id}",
        json={"status": "no_show"},
        headers=auth_headers(doctor.user),
    )
    assert again.status_code == 409


def test_cannot_mark_future_or_other_doctors_appointments(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    other_doctor = make_doctor(db, clinic=doctor.clinic)
    future_slot = make_slot(db, doctor, starts_in=timedelta(days=1), status=SlotStatus.BOOKED)
    booking = add_booking(db, future_slot, make_user(db))

    not_started = client.patch(
        f"/api/doctor/appointments/{booking.id}",
        json={"status": "no_show"},
        headers=auth_headers(doctor.user),
    )
    assert not_started.json()["error"]["code"] == "APPOINTMENT_NOT_STARTED"

    other = client.patch(
        f"/api/doctor/appointments/{booking.id}",
        json={"status": "completed"},
        headers=auth_headers(other_doctor.user),
    )
    assert other.status_code == 404

    invalid_status = client.patch(
        f"/api/doctor/appointments/{booking.id}",
        json={"status": "cancelled"},
        headers=auth_headers(doctor.user),
    )
    assert invalid_status.status_code == 422
