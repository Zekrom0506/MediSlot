from datetime import time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.timezones import local_to_utc
from app.models.enums import SlotStatus
from tests.factories import future_date, make_clinic, make_doctor, make_slot_at


def test_search_by_specialty_and_city(client: TestClient, db: Session) -> None:
    bengaluru = make_clinic(db, city="Bengaluru")
    mumbai = make_clinic(db, city="Mumbai")
    make_doctor(db, clinic=bengaluru, specialty="Cardiology", full_name="Dr. A")
    make_doctor(db, clinic=mumbai, specialty="Cardiology", full_name="Dr. B")
    make_doctor(db, clinic=mumbai, specialty="Dermatology", full_name="Dr. C")

    cardiology = client.get("/api/doctors?specialty=cardiology")
    assert [doctor["full_name"] for doctor in cardiology.json()] == ["Dr. A", "Dr. B"]

    mumbai_cardiology = client.get("/api/doctors?specialty=Cardiology&city=mumbai")
    assert [doctor["full_name"] for doctor in mumbai_cardiology.json()] == ["Dr. B"]


def test_search_hides_inactive_doctors_and_clinics(client: TestClient, db: Session) -> None:
    open_clinic = make_clinic(db)
    closed_clinic = make_clinic(db, city="Delhi")
    closed_clinic.is_active = False
    inactive_doctor = make_doctor(db, clinic=open_clinic)
    inactive_doctor.is_active = False
    db.commit()
    make_doctor(db, clinic=closed_clinic)
    visible_doctor = make_doctor(db, clinic=open_clinic)

    results = client.get("/api/doctors").json()
    assert [doctor["id"] for doctor in results] == [visible_doctor.id]

    profile = client.get(f"/api/doctors/{inactive_doctor.id}")
    assert profile.status_code == 404


def test_search_by_date_only_returns_doctors_with_free_slots(client: TestClient, db: Session) -> None:
    clinic = make_clinic(db)
    free_doctor = make_doctor(db, clinic=clinic)
    busy_doctor = make_doctor(db, clinic=clinic)
    day = future_date(2)
    make_slot_at(db, free_doctor, local_to_utc(day, time(10, 0)))
    make_slot_at(db, free_doctor, local_to_utc(day, time(11, 0)))
    make_slot_at(db, busy_doctor, local_to_utc(day, time(10, 0)), status=SlotStatus.BOOKED)
    make_slot_at(db, busy_doctor, local_to_utc(future_date(3), time(10, 0)))

    response = client.get(f"/api/doctors?date={day.isoformat()}")

    results = response.json()
    assert [doctor["id"] for doctor in results] == [free_doctor.id]
    assert results[0]["available_slot_count"] == 2


def test_search_rejects_past_date(client: TestClient) -> None:
    response = client.get(f"/api/doctors?date={future_date(-1).isoformat()}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_filters_list_specialties_and_cities(client: TestClient, db: Session) -> None:
    make_doctor(db, clinic=make_clinic(db, city="Mumbai"), specialty="ENT")
    make_doctor(db, clinic=make_clinic(db, city="Delhi"), specialty="Cardiology")

    filters = client.get("/api/doctors/filters").json()
    assert filters == {"specialties": ["Cardiology", "ENT"], "cities": ["Delhi", "Mumbai"]}


def test_available_slots_for_date(client: TestClient, db: Session) -> None:
    doctor = make_doctor(db)
    day = future_date(3)
    free_slot = make_slot_at(db, doctor, local_to_utc(day, time(9, 0)))
    make_slot_at(db, doctor, local_to_utc(day, time(9, 30)), status=SlotStatus.BLOCKED)
    make_slot_at(db, doctor, local_to_utc(future_date(4), time(9, 0)))

    response = client.get(f"/api/doctors/{doctor.id}/slots?date={day.isoformat()}")

    assert response.status_code == 200
    assert [slot["id"] for slot in response.json()] == [free_slot.id]


def test_slots_for_unknown_doctor_is_404(client: TestClient) -> None:
    response = client.get(f"/api/doctors/999/slots?date={future_date(1).isoformat()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCTOR_NOT_FOUND"


def test_unknown_route_uses_standard_error_shape(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
