from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timezones import local_day_bounds_utc, today_local
from app.models import Booking, Doctor, Slot, User
from app.models.enums import BookingStatus
from app.schemas.admin import AdminStats, BusyDoctor, DailyBookingCount


def safe_rate(part: int, whole: int) -> float:
    """part / whole, or 0 when there is nothing to divide by."""
    if whole == 0:
        return 0.0
    return round(part / whole, 3)


def count_bookings_by_status(db: Session, period_start: datetime) -> dict[str, int]:
    """{status: count} for bookings created since period_start."""
    query = (
        select(Booking.status, func.count(Booking.id))
        .where(Booking.created_at >= period_start)
        .group_by(Booking.status)
    )
    counts = {}
    for status, count in db.execute(query):
        counts[status] = count
    return counts


def bookings_per_day(db: Session, first_day: date, number_of_days: int) -> list[DailyBookingCount]:
    """Bookings created on each clinic-local day, including days with zero."""
    timezone_name = get_settings().clinic_timezone
    period_start, _ = local_day_bounds_utc(first_day)
    # Convert to clinic time inside Postgres before taking the date part,
    # otherwise late-evening bookings would be counted on the wrong day.
    local_day = func.date(func.timezone(timezone_name, Booking.created_at))
    query = (
        select(local_day, func.count(Booking.id))
        .where(Booking.created_at >= period_start)
        .group_by(local_day)
    )
    counts_by_day = {}
    for day, count in db.execute(query):
        counts_by_day[day] = count

    results = []
    for offset in range(number_of_days):
        day = first_day + timedelta(days=offset)
        results.append(DailyBookingCount(date=day, count=counts_by_day.get(day, 0)))
    return results


def busiest_doctors(db: Session, period_start: datetime, limit: int = 5) -> list[BusyDoctor]:
    """Doctors with the most non-cancelled bookings in the period."""
    booking_count = func.count(Booking.id).label("booking_count")
    query = (
        select(Doctor.id, User.full_name, Doctor.specialty, booking_count)
        .join(Slot, Slot.doctor_id == Doctor.id)
        .join(Booking, Booking.slot_id == Slot.id)
        .join(User, User.id == Doctor.user_id)
        .where(Booking.created_at >= period_start)
        .where(Booking.status != BookingStatus.CANCELLED.value)
        .group_by(Doctor.id, User.full_name, Doctor.specialty)
        .order_by(booking_count.desc(), Doctor.id)
        .limit(limit)
    )
    results = []
    for doctor_id, full_name, specialty, count in db.execute(query):
        results.append(
            BusyDoctor(doctor_id=doctor_id, full_name=full_name, specialty=specialty, booking_count=count)
        )
    return results


def get_admin_stats(db: Session, number_of_days: int) -> AdminStats:
    """Headline numbers for the admin dashboard over the last N days."""
    first_day = today_local() - timedelta(days=number_of_days - 1)
    period_start, _ = local_day_bounds_utc(first_day)

    status_counts = count_bookings_by_status(db, period_start)
    total = sum(status_counts.values())
    cancelled = status_counts.get(BookingStatus.CANCELLED.value, 0)
    completed = status_counts.get(BookingStatus.COMPLETED.value, 0)
    no_show = status_counts.get(BookingStatus.NO_SHOW.value, 0)

    return AdminStats(
        period_days=number_of_days,
        total_bookings=total,
        cancelled_bookings=cancelled,
        completed_bookings=completed,
        no_show_bookings=no_show,
        cancellation_rate=safe_rate(cancelled, total),
        # No-show rate only makes sense among appointments that already happened.
        no_show_rate=safe_rate(no_show, completed + no_show),
        bookings_per_day=bookings_per_day(db, first_day, number_of_days),
        busiest_doctors=busiest_doctors(db, period_start),
    )
