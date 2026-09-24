"""The most important test: many patients racing for the same slot."""

import threading

import httpx
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.models import Booking, Slot, User
from app.models.enums import BookingStatus, SlotStatus, UserRole
from tests.factories import TEST_PASSWORD_HASH, auth_headers, make_doctor, make_slot

NUMBER_OF_PATIENTS = 100


def create_patients(db: Session, count: int) -> list[User]:
    rows = []
    for number in range(count):
        rows.append(
            {
                "full_name": f"Racing Patient {number}",
                "email": f"racer{number}@example.com",
                "hashed_password": TEST_PASSWORD_HASH,
                "role": UserRole.PATIENT.value,
            }
        )
    db.execute(insert(User), rows)
    db.commit()
    return list(db.scalars(select(User).where(User.email.like("racer%"))))


def test_100_simultaneous_bookings_for_one_slot(db: Session, live_server_url: str) -> None:
    slot = make_slot(db, make_doctor(db))
    patients = create_patients(db, NUMBER_OF_PATIENTS)

    # Every thread waits at the barrier, so all 100 requests are released at the same moment.
    start_together = threading.Barrier(NUMBER_OF_PATIENTS)
    status_codes: list[int] = []
    error_codes: list[str] = []
    results_lock = threading.Lock()

    def try_to_book(patient: User) -> None:
        headers = auth_headers(patient)
        with httpx.Client(base_url=live_server_url, timeout=60) as http_client:
            start_together.wait()
            response = http_client.post("/api/bookings", json={"slot_id": slot.id}, headers=headers)
        with results_lock:
            status_codes.append(response.status_code)
            if response.status_code != 201:
                error_codes.append(response.json()["error"]["code"])

    threads = []
    for patient in patients:
        threads.append(threading.Thread(target=try_to_book, args=(patient,)))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert status_codes.count(201) == 1
    assert status_codes.count(409) == NUMBER_OF_PATIENTS - 1
    assert set(error_codes) == {"SLOT_ALREADY_BOOKED"}

    db.expire_all()
    confirmed_bookings = db.scalar(
        select(func.count(Booking.id))
        .where(Booking.slot_id == slot.id)
        .where(Booking.status == BookingStatus.CONFIRMED.value)
    )
    assert confirmed_bookings == 1
    assert db.get(Slot, slot.id).status == SlotStatus.BOOKED.value
