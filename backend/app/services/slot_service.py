from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.timezones import local_day_bounds_utc, local_to_utc, now_utc, today_local
from app.models import Doctor, Slot, WeeklySchedule
from app.models.enums import SlotStatus


def build_slot_times(
    schedule_entries: list[WeeklySchedule],
    local_date: date,
    appointment_length_minutes: int,
) -> list[tuple[datetime, datetime]]:
    """Cut the schedule blocks for one day into (start, end) pairs in UTC.

    A block of 09:00-10:00 with 20 minute appointments gives 09:00, 09:20 and 09:40.
    A leftover piece shorter than one appointment is dropped.
    """
    appointment_length = timedelta(minutes=appointment_length_minutes)
    slot_times = []
    for entry in schedule_entries:
        if entry.day_of_week != local_date.weekday():
            continue
        block_start = local_to_utc(local_date, entry.start_time)
        block_end = local_to_utc(local_date, entry.end_time)
        slot_start = block_start
        while slot_start + appointment_length <= block_end:
            slot_times.append((slot_start, slot_start + appointment_length))
            slot_start = slot_start + appointment_length
    return slot_times


def generate_slots_for_doctor(
    db: Session,
    doctor: Doctor,
    start_date: date | None = None,
    number_of_days: int | None = None,
) -> int:
    """Create missing slots for the coming days from the doctor's weekly schedule.

    Safe to run any number of times: ON CONFLICT DO NOTHING on the
    (doctor_id, start_time) unique constraint skips slots that already exist,
    including ones that were booked or blocked. Returns how many were created.
    """
    if start_date is None:
        start_date = today_local()
    if number_of_days is None:
        number_of_days = get_settings().slot_generation_days

    schedule_entries = list(db.scalars(select(WeeklySchedule).where(WeeklySchedule.doctor_id == doctor.id)))
    if not schedule_entries:
        return 0

    current_time = now_utc()
    new_rows = []
    for day_offset in range(number_of_days):
        local_date = start_date + timedelta(days=day_offset)
        for slot_start, slot_end in build_slot_times(
            schedule_entries, local_date, doctor.appointment_length_minutes
        ):
            if slot_start <= current_time:
                continue
            new_rows.append(
                {
                    "doctor_id": doctor.id,
                    "start_time": slot_start,
                    "end_time": slot_end,
                    "status": SlotStatus.AVAILABLE.value,
                }
            )

    if not new_rows:
        return 0

    statement = insert(Slot).values(new_rows)
    statement = statement.on_conflict_do_nothing(constraint="uq_slots_doctor_start_time")
    # RETURNING only gives back the rows that were really inserted, so we can count them.
    created_ids = list(db.scalars(statement.returning(Slot.id)))
    db.commit()
    return len(created_ids)


def generate_slots_for_all_doctors(db: Session) -> int:
    """Nightly job: top up slots for every active doctor."""
    total_created = 0
    active_doctors = db.scalars(select(Doctor).where(Doctor.is_active.is_(True)))
    for doctor in active_doctors:
        total_created += generate_slots_for_doctor(db, doctor)
    return total_created


def list_available_slots(db: Session, doctor_id: int, local_date: date) -> list[Slot]:
    """Free, future slots for a doctor on one clinic-local day, earliest first."""
    day_start, day_end = local_day_bounds_utc(local_date)
    query = (
        select(Slot)
        .where(Slot.doctor_id == doctor_id)
        .where(Slot.status == SlotStatus.AVAILABLE.value)
        .where(Slot.start_time >= max(day_start, now_utc()))
        .where(Slot.start_time < day_end)
        .order_by(Slot.start_time)
    )
    return list(db.scalars(query))


def list_all_slots_for_day(db: Session, doctor_id: int, local_date: date) -> list[Slot]:
    """Every slot (free, booked or blocked) for the doctor's own calendar view."""
    day_start, day_end = local_day_bounds_utc(local_date)
    query = (
        select(Slot)
        .where(Slot.doctor_id == doctor_id)
        .where(Slot.start_time >= day_start)
        .where(Slot.start_time < day_end)
        .order_by(Slot.start_time)
    )
    return list(db.scalars(query))


def lock_doctor_slot(db: Session, doctor: Doctor, slot_id: int) -> Slot:
    """Load one of the doctor's own slots with a row lock (SELECT ... FOR UPDATE)."""
    slot = db.scalar(select(Slot).where(Slot.id == slot_id).with_for_update())
    if slot is None or slot.doctor_id != doctor.id:
        raise NotFoundError("SLOT_NOT_FOUND", "Slot not found.")
    return slot


def block_slot(db: Session, doctor: Doctor, slot_id: int) -> Slot:
    """Mark a free slot as blocked so nobody can book it."""
    # The lock makes sure a patient cannot book this slot while we are blocking it.
    slot = lock_doctor_slot(db, doctor, slot_id)
    if slot.status == SlotStatus.BOOKED.value:
        db.rollback()
        raise ConflictError("SLOT_HAS_BOOKING", "This slot is booked. Cancel the appointment first.")
    slot.status = SlotStatus.BLOCKED.value
    db.commit()
    return slot


def unblock_slot(db: Session, doctor: Doctor, slot_id: int) -> Slot:
    """Make a blocked slot bookable again."""
    slot = lock_doctor_slot(db, doctor, slot_id)
    if slot.status != SlotStatus.BLOCKED.value:
        db.rollback()
        raise BusinessRuleError("SLOT_NOT_BLOCKED", "Only blocked slots can be unblocked.")
    if slot.start_time <= now_utc():
        db.rollback()
        raise BusinessRuleError("SLOT_IN_PAST", "Past slots cannot be unblocked.")
    slot.status = SlotStatus.AVAILABLE.value
    db.commit()
    return slot


def block_day(db: Session, doctor: Doctor, local_date: date) -> tuple[int, int]:
    """Block every free slot on a day (e.g. a holiday). Returns (blocked, still booked)."""
    day_start, day_end = local_day_bounds_utc(local_date)
    query = (
        select(Slot)
        .where(Slot.doctor_id == doctor.id)
        .where(Slot.start_time >= day_start)
        .where(Slot.start_time < day_end)
        .order_by(Slot.id)
        .with_for_update()
    )
    blocked_count = 0
    booked_count = 0
    for slot in db.scalars(query):
        if slot.status == SlotStatus.AVAILABLE.value:
            slot.status = SlotStatus.BLOCKED.value
            blocked_count += 1
        elif slot.status == SlotStatus.BOOKED.value:
            booked_count += 1
    db.commit()
    return blocked_count, booked_count
