from datetime import time

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.core.timezones import now_utc, to_local
from app.models import Booking, Doctor, Slot, WeeklySchedule
from app.models.enums import SlotStatus
from app.schemas.schedule import ScheduleEntry
from app.services import slot_service


def get_schedule(db: Session, doctor: Doctor) -> list[WeeklySchedule]:
    """The doctor's weekly schedule, ordered by day and start time."""
    query = (
        select(WeeklySchedule)
        .where(WeeklySchedule.doctor_id == doctor.id)
        .order_by(WeeklySchedule.day_of_week, WeeklySchedule.start_time)
    )
    return list(db.scalars(query))


def slot_fits_schedule(slot: Slot, entries: list[ScheduleEntry]) -> bool:
    """True if the slot lies completely inside one of the schedule blocks (clinic time)."""
    local_start = to_local(slot.start_time)
    local_end = to_local(slot.end_time)
    weekday = local_start.weekday()
    start_of_slot: time = local_start.time()
    end_of_slot: time = local_end.time()
    for entry in entries:
        if entry.day_of_week != weekday:
            continue
        if entry.start_time <= start_of_slot and end_of_slot <= entry.end_time:
            return True
    return False


def remove_slots_outside_schedule(db: Session, doctor: Doctor, entries: list[ScheduleEntry]) -> None:
    """Remove future free slots that the new schedule no longer covers.

    Slots that never had a booking are deleted. Slots that had one (for example a
    cancelled booking) must stay for history, so they are blocked instead.
    Booked slots are never touched.
    """
    future_free_slots = db.scalars(
        select(Slot)
        .where(Slot.doctor_id == doctor.id)
        .where(Slot.status == SlotStatus.AVAILABLE.value)
        .where(Slot.start_time > now_utc())
        .with_for_update()
    )
    for slot in future_free_slots:
        if slot_fits_schedule(slot, entries):
            continue
        has_booking_history = db.scalar(select(exists().where(Booking.slot_id == slot.id)))
        if has_booking_history:
            slot.status = SlotStatus.BLOCKED.value
        else:
            db.delete(slot)


def replace_schedule(db: Session, doctor: Doctor, entries: list[ScheduleEntry]) -> list[WeeklySchedule]:
    """Swap in a new weekly schedule and bring future slots in line with it."""
    db.execute(delete(WeeklySchedule).where(WeeklySchedule.doctor_id == doctor.id))
    for entry in entries:
        db.add(
            WeeklySchedule(
                doctor_id=doctor.id,
                day_of_week=entry.day_of_week,
                start_time=entry.start_time,
                end_time=entry.end_time,
            )
        )
    remove_slots_outside_schedule(db, doctor, entries)
    db.commit()

    slot_service.generate_slots_for_doctor(db, doctor)
    return get_schedule(db, doctor)
