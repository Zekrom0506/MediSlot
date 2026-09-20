from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from tests.factories import add_schedule, auth_headers, make_clinic, make_doctor, make_user

CLINIC_PAYLOAD = {"name": "City Care", "address": "22 MG Road", "city": "pune"}


def doctor_payload(clinic_id: int, email: str = "newdoc@example.com") -> dict:
    return {
        "full_name": "Dr. New Doctor",
        "email": email,
        "password": "DoctorPass1",
        "clinic_id": clinic_id,
        "specialty": "dermatology",
        "years_of_experience": 5,
        "consultation_fee": "650.00",
        "appointment_length_minutes": 20,
    }


def test_admin_can_create_and_list_clinics(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    response = client.post("/api/admin/clinics", json=CLINIC_PAYLOAD, headers=auth_headers(admin))

    assert response.status_code == 201
    assert response.json()["city"] == "Pune"

    listing = client.get("/api/admin/clinics", headers=auth_headers(admin))
    assert len(listing.json()) == 1


def test_non_admins_cannot_manage_clinics(client: TestClient, db: Session) -> None:
    patient = make_user(db, role=UserRole.PATIENT)
    doctor_user = make_user(db, role=UserRole.DOCTOR)

    no_login = client.post("/api/admin/clinics", json=CLINIC_PAYLOAD)
    as_patient = client.post("/api/admin/clinics", json=CLINIC_PAYLOAD, headers=auth_headers(patient))
    as_doctor = client.post("/api/admin/clinics", json=CLINIC_PAYLOAD, headers=auth_headers(doctor_user))

    assert no_login.status_code == 401
    assert as_patient.status_code == 403
    assert as_doctor.status_code == 403
    assert as_patient.json()["error"]["code"] == "FORBIDDEN"


def test_admin_can_update_and_deactivate_clinic(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    clinic = make_clinic(db)

    updated = client.patch(
        f"/api/admin/clinics/{clinic.id}", json={"name": "Renamed"}, headers=auth_headers(admin)
    )
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["city"] == "Bengaluru"

    deactivated = client.post(f"/api/admin/clinics/{clinic.id}/deactivate", headers=auth_headers(admin))
    assert deactivated.json()["is_active"] is False

    missing = client.patch("/api/admin/clinics/999", json={"name": "Nope"}, headers=auth_headers(admin))
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CLINIC_NOT_FOUND"


def test_admin_creates_doctor_with_login(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    clinic = make_clinic(db)

    response = client.post("/api/admin/doctors", json=doctor_payload(clinic.id), headers=auth_headers(admin))
    assert response.status_code == 201
    body = response.json()
    assert body["specialty"] == "Dermatology"
    assert body["clinic"]["id"] == clinic.id

    login = client.post("/api/auth/login", json={"email": "newdoc@example.com", "password": "DoctorPass1"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "doctor"


def test_create_doctor_rejects_duplicate_email_and_inactive_clinic(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    clinic = make_clinic(db)
    client.post("/api/admin/doctors", json=doctor_payload(clinic.id), headers=auth_headers(admin))

    duplicate = client.post("/api/admin/doctors", json=doctor_payload(clinic.id), headers=auth_headers(admin))
    assert duplicate.status_code == 409

    clinic.is_active = False
    db.commit()
    inactive = client.post(
        "/api/admin/doctors", json=doctor_payload(clinic.id, "other@example.com"), headers=auth_headers(admin)
    )
    assert inactive.status_code == 400
    assert inactive.json()["error"]["code"] == "CLINIC_INACTIVE"


def test_create_doctor_validates_input(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    payload = doctor_payload(1)
    payload["appointment_length_minutes"] = 2
    response = client.post("/api/admin/doctors", json=payload, headers=auth_headers(admin))
    assert response.status_code == 422


def test_admin_updates_lists_and_deactivates_doctor(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    doctor = make_doctor(db)

    updated = client.patch(
        f"/api/admin/doctors/{doctor.id}",
        json={"full_name": "Dr. Renamed", "consultation_fee": "999.50", "specialty": "neurology"},
        headers=auth_headers(admin),
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Dr. Renamed"
    assert updated.json()["specialty"] == "Neurology"

    listing = client.get("/api/admin/doctors", headers=auth_headers(admin))
    assert len(listing.json()) == 1

    deactivated = client.post(f"/api/admin/doctors/{doctor.id}/deactivate", headers=auth_headers(admin))
    assert deactivated.json()["is_active"] is False

    missing = client.post("/api/admin/doctors/999/deactivate", headers=auth_headers(admin))
    assert missing.status_code == 404


def test_admin_can_trigger_slot_generation(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    doctor = make_doctor(db)
    for day_of_week in range(7):
        add_schedule(db, doctor, day_of_week)

    response = client.post("/api/admin/slots/generate", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["created_count"] > 0
