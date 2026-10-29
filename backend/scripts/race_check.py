"""Race test through the load balancer: 100 patients book the same slot at the same instant.

The pytest version (tests/test_concurrency.py) talks to one API process. This one
goes through Nginx to however many API copies are running, to show that the
"exactly one winner" guarantee lives in PostgreSQL and not in any one process.

Run inside the stack (scripts/scale_test.sh does this):
    docker compose run --rm migrate python -m scripts.race_check http://frontend
"""

import json
import sys
import threading
import urllib.error
import urllib.request
import uuid
from collections import Counter

from sqlalchemy import func, insert, select

from app.core.database import SessionLocal
from app.core.security import create_access_token, hash_password
from app.core.timezones import now_utc
from app.models import Booking, Slot, User
from app.models.enums import BookingStatus, SlotStatus, UserRole

NUMBER_OF_PATIENTS = 100


def create_racers(run_id: str) -> list[User]:
    """Insert the patients straight into the database; one bcrypt hash is shared."""
    password_hash = hash_password(uuid.uuid4().hex)
    rows = [
        {
            "full_name": f"Racer {number}",
            "email": f"racer-{run_id}-{number}@example.com",
            "hashed_password": password_hash,
            "role": UserRole.PATIENT.value,
        }
        for number in range(NUMBER_OF_PATIENTS)
    ]
    with SessionLocal() as db:
        db.execute(insert(User), rows)
        db.commit()
        return list(db.scalars(select(User).where(User.email.like(f"racer-{run_id}-%"))))


def pick_free_slot() -> int:
    """The earliest free future slot of an active doctor."""
    with SessionLocal() as db:
        slot_id = db.scalar(
            select(Slot.id)
            .where(Slot.status == SlotStatus.AVAILABLE.value)
            .where(Slot.start_time > now_utc())
            .order_by(Slot.start_time, Slot.id)
            .limit(1)
        )
    if slot_id is None:
        sys.exit("No free slot found. Did the seed script run?")
    return slot_id


def main(base_url: str) -> None:
    run_id = uuid.uuid4().hex[:8]
    patients = create_racers(run_id)
    slot_id = pick_free_slot()
    start_together = threading.Barrier(len(patients))
    results: list[tuple[int, str, str]] = []
    results_lock = threading.Lock()

    def try_to_book(patient: User) -> None:
        request = urllib.request.Request(
            f"{base_url}/api/bookings",
            data=json.dumps({"slot_id": slot_id}).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {create_access_token(patient.id, patient.role)}",
            },
            method="POST",
        )
        start_together.wait()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, headers, body = response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            status, headers, body = error.code, error.headers, error.read()
        code = "BOOKED" if status == 201 else json.loads(body)["error"]["code"]
        with results_lock:
            results.append((status, code, headers.get("X-Served-By", "?")))

    threads = [threading.Thread(target=try_to_book, args=(patient,)) for patient in patients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with SessionLocal() as db:
        confirmed = db.scalar(
            select(func.count(Booking.id))
            .where(Booking.slot_id == slot_id)
            .where(Booking.status == BookingStatus.CONFIRMED.value)
        )

    status_counts = Counter(status for status, _, _ in results)
    # Errors raised before the app answers (e.g. PostgreSQL refused a connection) carry no
    # X-Served-By header; they are counted in "other", not as an extra instance.
    instances = Counter(served_by for _, _, served_by in results if served_by != "?")
    # Correct = never two winners. Other errors (e.g. a 500 because PostgreSQL ran out of
    # connections) are reported separately: they are a capacity problem, not a double booking.
    correct = status_counts.get(201) == 1 and confirmed == 1
    summary = {
        "requests": len(results),
        "status_201": status_counts.get(201, 0),
        "status_409": status_counts.get(409, 0),
        "other": {str(status): count for status, count in status_counts.items() if status not in (201, 409)},
        "confirmed_bookings_in_db": confirmed,
        "instances_that_answered": len(instances),
        "requests_per_instance": sorted(instances.values(), reverse=True),
        "correct": correct,
    }
    print(json.dumps(summary))
    sys.exit(0 if correct else 1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://frontend")
