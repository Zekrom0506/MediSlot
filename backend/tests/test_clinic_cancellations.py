"""When the clinic side cancels: a doctor cancels one visit, or a doctor or clinic is deactivated."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Notification, Slot
from app.models.enums import BookingStatus, SlotStatus, UserRole
from app.services import notification_service
from tests.factories import auth_headers, make_doctor, make_slot, make_user


class RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to_address: str, subject: str, body: str) -> None:
        self.sent.append((to_address, subject, body))


def book(client: TestClient, patient, slot_id: int) -> int:
    response = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_headers(patient))
    assert response.status_code == 201
    return response.json()["id"]


def cancellation_notifications(db: Session) -> list[Notification]:
    db.expire_all()
    return list(
        db.scalars(select(Notification).where(Notification.type == "cancellation").order_by(Notification.id))
    )


def test_doctor_cancels_an_appointment_and_the_patient_is_told(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    patient = make_user(db)
    slot = make_slot(db, doctor)
    booking_id = book(client, patient, slot.id)

    response = client.post(f"/api/doctor/appointments/{booking_id}/cancel", headers=auth_headers(doctor.user))

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    db.expire_all()
    assert db.get(Booking, booking_id).cancelled_by == "clinic"
    # Blocked, not freed: the doctor is not available at that time.
    assert db.get(Slot, slot.id).status == SlotStatus.BLOCKED.value

    patient_view = client.get(f"/api/bookings/{booking_id}", headers=auth_headers(patient)).json()
    assert patient_view["cancelled_by"] == "clinic"

    [notification] = cancellation_notifications(db)
    sender = RecordingEmailSender()
    notification_service.deliver_notification(db, notification.id, sender)
    assert "The clinic cancelled it" in sender.sent[0][2]


def test_doctor_can_only_cancel_own_upcoming_confirmed_appointments(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    other_doctor = make_doctor(db, clinic=doctor.clinic)
    booking_id = book(client, make_user(db), make_slot(db, doctor).id)
    started_slot = make_slot(db, doctor, starts_in=timedelta(minutes=-10), status=SlotStatus.BOOKED)
    started = Booking(
        patient_id=make_user(db).id, slot_id=started_slot.id, status=BookingStatus.CONFIRMED.value
    )
    db.add(started)
    db.commit()

    not_mine = client.post(
        f"/api/doctor/appointments/{booking_id}/cancel", headers=auth_headers(other_doctor.user)
    )
    already_started = client.post(
        f"/api/doctor/appointments/{started.id}/cancel", headers=auth_headers(doctor.user)
    )
    client.post(f"/api/doctor/appointments/{booking_id}/cancel", headers=auth_headers(doctor.user))
    twice = client.post(f"/api/doctor/appointments/{booking_id}/cancel", headers=auth_headers(doctor.user))

    assert not_mine.status_code == 404
    assert already_started.status_code == 400
    assert twice.status_code == 409


def test_deactivating_a_doctor_cancels_upcoming_appointments_only(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    doctor = make_doctor(db)
    upcoming_ids = [
        book(client, make_user(db), make_slot(db, doctor, starts_in=timedelta(days=days)).id)
        for days in (1, 2)
    ]
    past_slot = make_slot(db, doctor, starts_in=timedelta(days=-1), status=SlotStatus.BOOKED)
    past = Booking(patient_id=make_user(db).id, slot_id=past_slot.id, status=BookingStatus.COMPLETED.value)
    db.add(past)
    db.commit()

    response = client.post(f"/api/admin/doctors/{doctor.id}/deactivate", headers=auth_headers(admin))

    assert response.status_code == 200
    db.expire_all()
    for booking_id in upcoming_ids:
        booking = db.get(Booking, booking_id)
        assert (booking.status, booking.cancelled_by) == ("cancelled", "clinic")
    assert db.get(Booking, past.id).status == BookingStatus.COMPLETED.value
    assert {row.booking_id for row in cancellation_notifications(db)} == set(upcoming_ids)


def test_patching_is_active_false_also_cancels_appointments(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    doctor = make_doctor(db)
    booking_id = book(client, make_user(db), make_slot(db, doctor).id)

    response = client.patch(
        f"/api/admin/doctors/{doctor.id}", json={"is_active": False}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    db.expire_all()
    assert db.get(Booking, booking_id).status == BookingStatus.CANCELLED.value


def test_deactivating_a_clinic_cancels_its_doctors_appointments(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    doctor = make_doctor(db)
    colleague = make_doctor(db, clinic=doctor.clinic)
    elsewhere = make_doctor(db)
    patient = make_user(db)
    ids = [
        book(client, patient, make_slot(db, doctor, starts_in=timedelta(days=1)).id),
        book(client, patient, make_slot(db, colleague, starts_in=timedelta(days=2)).id),
    ]
    other_id = book(client, patient, make_slot(db, elsewhere, starts_in=timedelta(days=3)).id)

    response = client.post(f"/api/admin/clinics/{doctor.clinic_id}/deactivate", headers=auth_headers(admin))

    assert response.status_code == 200
    db.expire_all()
    assert [db.get(Booking, booking_id).status for booking_id in ids] == ["cancelled", "cancelled"]
    assert db.get(Booking, other_id).status == BookingStatus.CONFIRMED.value


def test_deactivated_doctor_cannot_use_the_doctor_portal(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    doctor.is_active = False
    db.commit()

    response = client.get("/api/doctor/appointments", headers=auth_headers(doctor.user))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DOCTOR_INACTIVE"
