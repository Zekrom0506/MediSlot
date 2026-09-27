"""Booking rules: book, cancel, reschedule, and appointment outcomes.

Locking rules used everywhere in this file, so that no two transactions can
wait for each other in a circle (a deadlock):
  1. lock the booking row first (if there is one),
  2. then lock slot rows, always in increasing id order.
"""

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.timezones import local_day_bounds_utc, now_utc, today_local
from app.models import Booking, Doctor, Slot, User
from app.models.enums import BookingStatus, SlotStatus
from app.services import cache_service

SLOT_TAKEN_MESSAGE = "Sorry, this slot was just booked. Please choose another slot."


def slot_taken_error() -> ConflictError:
    return ConflictError("SLOT_ALREADY_BOOKED", SLOT_TAKEN_MESSAGE)


def can_cancel(slot_start: datetime, current_time: datetime) -> bool:
    """Bookings can be cancelled until a fixed number of hours before they start."""
    deadline = slot_start - timedelta(hours=get_settings().cancellation_deadline_hours)
    return current_time <= deadline


def lock_slot(db: Session, slot_id: int) -> Slot:
    """SELECT ... FOR UPDATE on one slot.

    Any other transaction that tries to lock the same slot waits here until we
    commit or roll back, so only one request at a time can change a slot.
    """
    slot = db.scalar(select(Slot).where(Slot.id == slot_id).with_for_update())
    if slot is None:
        raise NotFoundError("SLOT_NOT_FOUND", "Slot not found.")
    return slot


def lock_own_booking(db: Session, patient: User, booking_id: int) -> Booking:
    """Lock a booking and check it belongs to the patient and is still active."""
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "Booking not found.")
    if booking.patient_id != patient.id:
        raise PermissionDeniedError("FORBIDDEN", "You can only change your own bookings.")
    if booking.status != BookingStatus.CONFIRMED.value:
        raise ConflictError("BOOKING_NOT_ACTIVE", "This booking is no longer active.")
    return booking


def ensure_slot_is_bookable(db: Session, slot: Slot) -> None:
    """Check a *locked* slot can be booked right now."""
    if slot.status == SlotStatus.BOOKED.value:
        raise slot_taken_error()
    if slot.status != SlotStatus.AVAILABLE.value:
        raise ConflictError("SLOT_NOT_AVAILABLE", "This slot is not available for booking.")
    if slot.start_time <= now_utc():
        raise BusinessRuleError("SLOT_IN_PAST", "This slot has already started.")
    doctor = db.get(Doctor, slot.doctor_id)
    if doctor is None or not doctor.is_active:
        raise ConflictError("SLOT_NOT_AVAILABLE", "This doctor is not taking bookings.")


def commit_or_slot_taken(db: Session) -> None:
    """Commit, turning a hit on the one-confirmed-booking-per-slot index into a 409.

    With the row lock above this should never happen; the index is the
    second line of defence if some other code path forgets to lock.
    """
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise slot_taken_error()


def reserve_slot(db: Session, patient: User, slot_id: int, reason_for_visit: str | None) -> Booking:
    """Lock the slot, check it, and add the booking to the open transaction.

    Does not commit, so the caller can save more rows (like an idempotency key)
    in the same transaction before calling commit_or_slot_taken().
    """
    try:
        slot = lock_slot(db, slot_id)
        ensure_slot_is_bookable(db, slot)
    except Exception:
        # Release the lock straight away instead of when the session closes.
        db.rollback()
        raise

    booking = Booking(
        patient_id=patient.id,
        slot_id=slot.id,
        status=BookingStatus.CONFIRMED.value,
        reason_for_visit=reason_for_visit,
    )
    slot.status = SlotStatus.BOOKED.value
    db.add(booking)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise slot_taken_error()
    return booking


def book_slot(db: Session, patient: User, slot_id: int, reason_for_visit: str | None) -> Booking:
    """Book a slot for a patient. Exactly one of many concurrent requests can win."""
    booking = reserve_slot(db, patient, slot_id, reason_for_visit)
    commit_or_slot_taken(db)
    # Only after the commit: invalidating earlier could let a reader re-cache the old state.
    cache_service.invalidate_slot_day(booking.slot.doctor_id, booking.slot.start_time)
    return booking


def cancel_booking(db: Session, patient: User, booking_id: int) -> Booking:
    """Cancel a booking and free its slot, if it is not too close to the start time."""
    try:
        booking = lock_own_booking(db, patient, booking_id)
        slot = lock_slot(db, booking.slot_id)
        if not can_cancel(slot.start_time, now_utc()):
            hours = get_settings().cancellation_deadline_hours
            raise BusinessRuleError(
                "CANCELLATION_WINDOW_CLOSED",
                f"Bookings can only be cancelled up to {hours} hours before the appointment.",
            )
    except Exception:
        db.rollback()
        raise

    booking.status = BookingStatus.CANCELLED.value
    booking.cancelled_at = now_utc()
    slot.status = SlotStatus.AVAILABLE.value
    db.commit()
    cache_service.invalidate_slot_day(slot.doctor_id, slot.start_time)
    return booking


def reschedule_booking(db: Session, patient: User, booking_id: int, new_slot_id: int) -> Booking:
    """Move a booking to another slot of the same doctor in a single transaction.

    Either everything happens (old booking cancelled, old slot freed, new booking
    created, new slot taken) or nothing does, so the patient never ends up with
    zero or two bookings.
    """
    try:
        old_booking = lock_own_booking(db, patient, booking_id)
        if old_booking.slot_id == new_slot_id:
            raise BusinessRuleError("SAME_SLOT", "The booking is already in this slot.")

        # Always lock the lower id first. If two reschedules swap slots A and B at the
        # same moment, both try A first, so one simply waits instead of deadlocking.
        locked_slots = {}
        for slot_id in sorted([old_booking.slot_id, new_slot_id]):
            locked_slots[slot_id] = lock_slot(db, slot_id)
        old_slot = locked_slots[old_booking.slot_id]
        new_slot = locked_slots[new_slot_id]

        if new_slot.doctor_id != old_slot.doctor_id:
            raise BusinessRuleError(
                "DIFFERENT_DOCTOR", "You can only reschedule to a slot with the same doctor."
            )
        if not can_cancel(old_slot.start_time, now_utc()):
            raise BusinessRuleError(
                "CANCELLATION_WINDOW_CLOSED", "It is too close to the appointment to reschedule it."
            )
        ensure_slot_is_bookable(db, new_slot)
    except Exception:
        db.rollback()
        raise

    old_booking.status = BookingStatus.CANCELLED.value
    old_booking.cancelled_at = now_utc()
    old_slot.status = SlotStatus.AVAILABLE.value

    new_booking = Booking(
        patient_id=patient.id,
        slot_id=new_slot.id,
        status=BookingStatus.CONFIRMED.value,
        reason_for_visit=old_booking.reason_for_visit,
    )
    new_slot.status = SlotStatus.BOOKED.value
    db.add(new_booking)
    commit_or_slot_taken(db)
    cache_service.invalidate_slot_day(old_slot.doctor_id, old_slot.start_time)
    cache_service.invalidate_slot_day(new_slot.doctor_id, new_slot.start_time)
    return new_booking


def bookings_with_details_query() -> Select[tuple[Booking]]:
    """Base query that loads slot, doctor, clinic and patient in one go."""
    return (
        select(Booking)
        .join(Booking.slot)
        .options(joinedload(Booking.slot).joinedload(Slot.doctor))
        .options(joinedload(Booking.patient))
    )


def get_booking_for_patient(db: Session, patient: User, booking_id: int) -> Booking:
    """One booking with all details, only if it belongs to the patient."""
    booking = db.scalar(bookings_with_details_query().where(Booking.id == booking_id))
    if booking is None:
        raise NotFoundError("BOOKING_NOT_FOUND", "Booking not found.")
    if booking.patient_id != patient.id:
        raise PermissionDeniedError("FORBIDDEN", "You can only view your own bookings.")
    return booking


def list_patient_bookings(db: Session, patient: User, scope: Literal["upcoming", "past"]) -> list[Booking]:
    """Upcoming = confirmed and in the future. Past = everything else (history)."""
    current_time = now_utc()
    query = bookings_with_details_query().where(Booking.patient_id == patient.id)
    if scope == "upcoming":
        query = (
            query.where(Booking.status == BookingStatus.CONFIRMED.value)
            .where(Slot.start_time >= current_time)
            .order_by(Slot.start_time)
        )
    else:
        is_upcoming = (Booking.status == BookingStatus.CONFIRMED.value) & (Slot.start_time >= current_time)
        query = query.where(~is_upcoming).order_by(Slot.start_time.desc())
    return list(db.scalars(query))


def list_doctor_appointments(
    db: Session, doctor: Doctor, scope: Literal["today", "upcoming"]
) -> list[Booking]:
    """Today's appointments (any outcome except cancelled), or all future confirmed ones."""
    query = bookings_with_details_query().where(Slot.doctor_id == doctor.id).order_by(Slot.start_time)
    if scope == "today":
        day_start, day_end = local_day_bounds_utc(today_local())
        query = (
            query.where(Slot.start_time >= day_start)
            .where(Slot.start_time < day_end)
            .where(Booking.status != BookingStatus.CANCELLED.value)
        )
    else:
        query = query.where(Slot.start_time >= now_utc()).where(
            Booking.status == BookingStatus.CONFIRMED.value
        )
    return list(db.scalars(query))


def record_appointment_outcome(
    db: Session, doctor: Doctor, booking_id: int, outcome: Literal["completed", "no_show"]
) -> Booking:
    """Doctor marks an appointment that has started as completed or no-show."""
    try:
        booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
        if booking is None or booking.slot.doctor_id != doctor.id:
            raise NotFoundError("BOOKING_NOT_FOUND", "Appointment not found.")
        if booking.status != BookingStatus.CONFIRMED.value:
            raise ConflictError("BOOKING_NOT_ACTIVE", "Only confirmed appointments can be updated.")
        if booking.slot.start_time > now_utc():
            raise BusinessRuleError("APPOINTMENT_NOT_STARTED", "This appointment has not started yet.")
    except Exception:
        db.rollback()
        raise

    booking.status = outcome
    db.commit()
    return booking
