from datetime import time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Slot
from app.models.enums import SlotStatus, UserRole
from app.services import slot_service
from tests.factories import (
    add_schedule,
    auth_headers,
    future_date,
    make_doctor,
    make_slot,
    make_user,
)


def every_day_schedule(start: str = "09:00", end: str = "10:00") -> dict:
    entries = []
    for day_of_week in range(7):
        entries.append({"day_of_week": day_of_week, "start_time": start, "end_time": end})
    return {"entries": entries}


def test_doctor_sees_own_profile(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db, full_name="Dr. Own")
    response = client.get("/api/doctor/me", headers=auth_headers(doctor.user))
    assert response.json()["full_name"] == "Dr. Own"


def test_doctor_without_profile_gets_404(client: TestClient, db: Session) -> None:
    lonely_doctor_user = make_user(db, role=UserRole.DOCTOR)
    response = client.get("/api/doctor/me", headers=auth_headers(lonely_doctor_user))
    assert response.status_code == 404


def test_patient_cannot_use_doctor_portal(client: TestClient, db: Session) -> None:
    patient = make_user(db)
    response = client.get("/api/doctor/schedule", headers=auth_headers(patient))
    assert response.status_code == 403


def test_setting_schedule_generates_slots(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db, appointment_length_minutes=30)

    response = client.put(
        "/api/doctor/schedule", json=every_day_schedule(), headers=auth_headers(doctor.user)
    )

    assert response.status_code == 200
    assert len(response.json()) == 7
    tomorrow_slots = slot_service.list_available_slots(db, doctor.id, future_date(1))
    assert len(tomorrow_slots) == 2

    read_back = client.get("/api/doctor/schedule", headers=auth_headers(doctor.user))
    assert read_back.json()[0]["start_time"] == "09:00:00"


def test_schedule_rejects_overlaps_and_reversed_times(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    overlapping = {
        "entries": [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "12:00"},
            {"day_of_week": 0, "start_time": "11:00", "end_time": "13:00"},
        ]
    }
    reversed_times = {"entries": [{"day_of_week": 1, "start_time": "12:00", "end_time": "09:00"}]}
    bad_day = {"entries": [{"day_of_week": 7, "start_time": "09:00", "end_time": "10:00"}]}

    for payload in (overlapping, reversed_times, bad_day):
        response = client.put("/api/doctor/schedule", json=payload, headers=auth_headers(doctor.user))
        assert response.status_code == 422


def test_changing_schedule_removes_free_slots_outside_it(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db, appointment_length_minutes=30)
    client.put(
        "/api/doctor/schedule", json=every_day_schedule("09:00", "11:00"), headers=auth_headers(doctor.user)
    )
    slots_before = slot_service.list_available_slots(db, doctor.id, future_date(1))
    assert len(slots_before) == 4

    # Give the 10:00 slot a cancelled booking, so it has history and must be kept.
    slot_with_history = slots_before[2]
    deleted_slot_id = slots_before[3].id
    patient = make_user(db)
    db.add(Booking(patient_id=patient.id, slot_id=slot_with_history.id, status="cancelled"))
    db.commit()

    client.put(
        "/api/doctor/schedule", json=every_day_schedule("09:00", "10:00"), headers=auth_headers(doctor.user)
    )

    db.expire_all()
    slots_after = slot_service.list_available_slots(db, doctor.id, future_date(1))
    assert len(slots_after) == 2
    assert db.get(Slot, slot_with_history.id).status == SlotStatus.BLOCKED.value
    assert db.get(Slot, deleted_slot_id) is None


def test_block_and_unblock_slot(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    slot = make_slot(db, doctor)
    headers = auth_headers(doctor.user)

    blocked = client.post(f"/api/doctor/slots/{slot.id}/block", headers=headers)
    assert blocked.json()["status"] == "blocked"

    unblocked = client.post(f"/api/doctor/slots/{slot.id}/unblock", headers=headers)
    assert unblocked.json()["status"] == "available"

    unblock_again = client.post(f"/api/doctor/slots/{slot.id}/unblock", headers=headers)
    assert unblock_again.status_code == 400


def test_cannot_block_booked_slot_or_other_doctors_slot(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    other_doctor = make_doctor(db, clinic=doctor.clinic)
    booked_slot = make_slot(db, doctor, status=SlotStatus.BOOKED)
    other_slot = make_slot(db, other_doctor)

    booked = client.post(f"/api/doctor/slots/{booked_slot.id}/block", headers=auth_headers(doctor.user))
    assert booked.status_code == 409
    assert booked.json()["error"]["code"] == "SLOT_HAS_BOOKING"

    not_mine = client.post(f"/api/doctor/slots/{other_slot.id}/block", headers=auth_headers(doctor.user))
    assert not_mine.status_code == 404


def test_cannot_unblock_past_slot(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    past_slot = make_slot(db, doctor, starts_in=timedelta(hours=-3), status=SlotStatus.BLOCKED)
    response = client.post(f"/api/doctor/slots/{past_slot.id}/unblock", headers=auth_headers(doctor.user))
    assert response.json()["error"]["code"] == "SLOT_IN_PAST"


def test_block_whole_day_leaves_booked_slots(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db, appointment_length_minutes=60)
    day = future_date(3)
    add_schedule(db, doctor, day.weekday(), time(9, 0), time(12, 0))
    slot_service.generate_slots_for_doctor(db, doctor, day, number_of_days=1)
    first_slot = db.scalars(select(Slot).where(Slot.doctor_id == doctor.id).order_by(Slot.start_time)).first()
    first_slot.status = SlotStatus.BOOKED.value
    db.commit()

    response = client.post(
        "/api/doctor/block-day", json={"date": day.isoformat()}, headers=auth_headers(doctor.user)
    )

    assert response.json() == {"blocked_count": 2, "booked_count": 1}
    day_view = client.get(f"/api/doctor/slots?date={day.isoformat()}", headers=auth_headers(doctor.user))
    statuses = [slot["status"] for slot in day_view.json()]
    assert statuses == ["booked", "blocked", "blocked"]


def test_block_day_rejects_past_date(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    response = client.post(
        "/api/doctor/block-day", json={"date": future_date(-1).isoformat()}, headers=auth_headers(doctor.user)
    )
    assert response.status_code == 422
