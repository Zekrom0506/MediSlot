from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.timezones import today_local
from app.models import Booking
from app.models.enums import BookingStatus, SlotStatus, UserRole
from app.services.stats_service import safe_rate
from tests.factories import auth_headers, make_doctor, make_slot, make_user


def add_booking(db: Session, doctor, status: BookingStatus) -> None:
    hours_ahead = db.query(Booking).count() + 1
    slot = make_slot(db, doctor, starts_in=timedelta(hours=hours_ahead), status=SlotStatus.BOOKED)
    db.add(Booking(patient_id=make_user(db).id, slot_id=slot.id, status=status.value))
    db.commit()


def test_safe_rate_handles_zero() -> None:
    assert safe_rate(0, 0) == 0.0
    assert safe_rate(1, 3) == 0.333


def test_admin_stats(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    busy_doctor = make_doctor(db, full_name="Dr. Busy")
    quiet_doctor = make_doctor(db, clinic=busy_doctor.clinic, full_name="Dr. Quiet")
    add_booking(db, busy_doctor, BookingStatus.CONFIRMED)
    add_booking(db, busy_doctor, BookingStatus.COMPLETED)
    add_booking(db, busy_doctor, BookingStatus.COMPLETED)
    add_booking(db, busy_doctor, BookingStatus.NO_SHOW)
    add_booking(db, quiet_doctor, BookingStatus.CANCELLED)

    response = client.get("/api/admin/stats?days=7", headers=auth_headers(admin))

    assert response.status_code == 200
    stats = response.json()
    assert stats["total_bookings"] == 5
    assert stats["cancellation_rate"] == 0.2
    assert stats["no_show_rate"] == 0.333
    assert len(stats["bookings_per_day"]) == 7
    assert stats["bookings_per_day"][-1] == {"date": today_local().isoformat(), "count": 5}
    assert stats["busiest_doctors"][0]["full_name"] == "Dr. Busy"
    assert stats["busiest_doctors"][0]["booking_count"] == 4
    # Dr. Quiet only has a cancelled booking, which does not count as busy.
    assert len(stats["busiest_doctors"]) == 1


def test_stats_are_admin_only(client: TestClient, db: Session) -> None:
    response = client.get("/api/admin/stats", headers=auth_headers(make_user(db)))
    assert response.status_code == 403
