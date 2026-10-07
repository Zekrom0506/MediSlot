"""Simulated patients for load testing MediSlot.

Each simulated user logs in as one of the seeded demo patients, then mostly
browses (search, open a doctor, look at free times) and sometimes books or
cancels, roughly like real patients do.

    locust -f load_tests/locustfile.py --host http://localhost:3000
"""

import itertools
import random
import threading
import uuid
from datetime import date, timedelta

from locust import HttpUser, between, task

DEMO_PASSWORD = "Demo@1234"
SPECIALTIES = ["Cardiology", "Dermatology", "General Medicine", "Pediatrics", "ENT", "Orthopedics"]
CITIES = ["Bengaluru", "Mumbai", "Delhi"]

# Hand out seeded patient accounts one by one, so users do not share a login.
patient_numbers = itertools.cycle(range(1, 50))
patient_numbers_lock = threading.Lock()


def next_patient_email() -> str:
    with patient_numbers_lock:
        number = next(patient_numbers)
    return f"patient{number}@medislot.dev"


def random_upcoming_date() -> str:
    return (date.today() + timedelta(days=random.randint(1, 10))).isoformat()


class Patient(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"email": next_patient_email(), "password": DEMO_PASSWORD},
            name="POST /api/auth/login",
        )
        token = response.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"
        self.doctor_ids: list[int] = []
        self.booking_ids: list[int] = []

    @task(5)
    def search_doctors(self) -> None:
        params = {"specialty": random.choice(SPECIALTIES), "city": random.choice(CITIES)}
        if random.random() < 0.5:
            params["date"] = random_upcoming_date()
        response = self.client.get("/api/doctors", params=params, name="GET /api/doctors")
        if response.ok:
            for doctor in response.json():
                if doctor["id"] not in self.doctor_ids:
                    self.doctor_ids.append(doctor["id"])

    @task(5)
    def view_slots(self) -> None:
        doctor_id = self.pick_doctor()
        self.client.get(
            f"/api/doctors/{doctor_id}/slots",
            params={"date": random_upcoming_date()},
            name="GET /api/doctors/[id]/slots",
        )

    @task(2)
    def book_slot(self) -> None:
        doctor_id = self.pick_doctor()
        slots_response = self.client.get(
            f"/api/doctors/{doctor_id}/slots",
            params={"date": random_upcoming_date()},
            name="GET /api/doctors/[id]/slots",
        )
        free_slots = slots_response.json() if slots_response.ok else []
        if not free_slots:
            return
        slot = random.choice(free_slots)

        with self.client.post(
            "/api/bookings",
            json={"slot_id": slot["id"], "reason_for_visit": "Load test visit"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
            name="POST /api/bookings",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.booking_ids.append(response.json()["id"])
                response.success()
            elif response.status_code in (409, 429):
                # Losing a race for a slot or hitting the per-user limit is correct behaviour.
                response.success()
            else:
                response.failure(f"unexpected status {response.status_code}")

    @task(2)
    def my_appointments(self) -> None:
        self.client.get("/api/bookings/me", params={"scope": "upcoming"}, name="GET /api/bookings/me")

    @task(1)
    def cancel_booking(self) -> None:
        if not self.booking_ids:
            return
        booking_id = self.booking_ids.pop()
        self.client.post(f"/api/bookings/{booking_id}/cancel", name="POST /api/bookings/[id]/cancel")

    def pick_doctor(self) -> int:
        if self.doctor_ids:
            return random.choice(self.doctor_ids)
        return random.randint(1, 10)
