"""Booking rules: book, cancel, reschedule, and appointment outcomes.

Locking rules used everywhere in this file, so that no two transactions can
wait for each other in a circle (a deadlock). Rows are always locked in this
order, skipping the ones a change does not need:
  1. the patient's user row (serialises one patient's bookings, so the
     per-patient limits below cannot be beaten with parallel requests),
  2. the doctor row: FOR KEY SHARE when booking (many patients at once are fine),
     FOR UPDATE when deactivating a doctor or clinic (waits for those bookings),
  3. booking rows, in increasing id order,
  4. slot rows, in increasing id order.
"""

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.metrics import BOOKING_CONFLICTS, BOOKINGS_CANCELLED, BOOKINGS_CREATED
from app.core.timezones import local_day_bounds_utc, now_utc, today_local
from app.models import Booking, Clinic, Doctor, Slot, User
from app.models.enums import BookingStatus, CancelledBy, NotificationType, SlotStatus
from app.services import cache_service, notification_service

SLOT_TAKEN_MESSAGE = "Sorry, this slot was just booked. Please choose another slot."


def slot_taken_error() -> ConflictError:
    BOOKING_CONFLICTS.inc()
    return ConflictError("SLOT_ALREADY_BOOKED", SLOT_TAKEN_MESSAGE)


def can_cancel(slot_start: datetime, current_time: datetime) -> bool:
    """Bookings can be cancelled until a fixed number of hours before they start."""
    deadline = slot_start - timedelta(hours=get_settings().cancellation_deadline_hours)
    return current_time <= deadline


def lock_patient(db: Session, patient: User) -> None:
    """SELECT ... FOR UPDATE on the patient's own row (step 1 of the lock order)."""
    db.execute(select(User.id).where(User.id == patient.id).with_for_update())


def find_slot_doctor_id(db: Session, slot_id: int) -> int:
    """Which doctor a slot belongs to. Read without a lock: it never changes."""
    doctor_id = db.scalar(select(Slot.doctor_id).where(Slot.id == slot_id))
    if doctor_id is None:
        raise NotFoundError("SLOT_NOT_FOUND", "Slot not found.")
    return doctor_id


def lock_doctor_for_booking(db: Session, doctor_id: int) -> None:
    """FOR KEY SHARE on the doctor, then check the doctor and clinic still take bookings.

    Many bookings can hold this lock at once, and ordinary profile edits do not
    wait for it. Deactivating the doctor or their clinic takes FOR UPDATE, which
    waits for these bookings to finish, and they wait for it. So no booking can
    slip in while a doctor's upcoming appointments are being cancelled.
    """
    doctor_row = db.execute(
        select(Doctor.is_active, Doctor.clinic_id)
        .where(Doctor.id == doctor_id)
        .with_for_update(read=True, key_share=True)
    ).one_or_none()
    # A separate query (new snapshot) so a clinic deactivated while we waited is seen.
    clinic_active = doctor_row is not None and db.scalar(
        select(Clinic.is_active).where(Clinic.id == doctor_row.clinic_id)
    )
    if doctor_row is None or not doctor_row.is_active or not clinic_active:
        raise ConflictError("SLOT_NOT_AVAILABLE", "This doctor is not taking bookings.")


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


def ensure_patient_can_book(
    db: Session, patient: User, slot: Slot, replacing_booking_id: int | None = None
) -> None:
    """Per-patient limits, checked while the patient's row is locked.

    - one upcoming appointment per doctor (move it with reschedule instead),
    - no two appointments at overlapping times,
    - at most `max_upcoming_bookings_per_patient` upcoming appointments.
    A reschedule passes the booking it replaces, which is left out of the checks.
    """
    upcoming = (
        select(Booking.id, Slot.doctor_id, Slot.start_time, Slot.end_time)
        .join(Booking.slot)
        .where(Booking.patient_id == patient.id)
        .where(Booking.status == BookingStatus.CONFIRMED.value)
        .where(Slot.end_time > now_utc())
    )
    if replacing_booking_id is not None:
        upcoming = upcoming.where(Booking.id != replacing_booking_id)
    other_bookings = db.execute(upcoming).all()

    for _, doctor_id, start_time, end_time in other_bookings:
        if doctor_id == slot.doctor_id:
            raise ConflictError(
                "ALREADY_BOOKED_WITH_DOCTOR",
                "You already have an upcoming appointment with this doctor. Reschedule it instead.",
            )
        if start_time < slot.end_time and slot.start_time < end_time:
            raise ConflictError("OVERLAPPING_BOOKING", "You already have another appointment at this time.")
    limit = get_settings().max_upcoming_bookings_per_patient
    if len(other_bookings) >= limit:
        raise ConflictError(
            "TOO_MANY_BOOKINGS",
            f"You can have at most {limit} upcoming appointments. Cancel one to book another.",
        )


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
        lock_patient(db, patient)
        lock_doctor_for_booking(db, find_slot_doctor_id(db, slot_id))
        slot = lock_slot(db, slot_id)
        ensure_slot_is_bookable(db, slot)
        ensure_patient_can_book(db, patient, slot)
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
    BOOKINGS_CREATED.inc()
    # Only after the commit: invalidating earlier could let a reader re-cache the old state.
    cache_service.invalidate_slot_day(booking.slot.doctor_id, booking.slot.start_time)
    notification_service.notify_booking(db, booking.id, NotificationType.CONFIRMATION)
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
    booking.cancelled_by = CancelledBy.PATIENT.value
    slot.status = SlotStatus.AVAILABLE.value
    db.commit()
    BOOKINGS_CANCELLED.inc()
    cache_service.invalidate_slot_day(slot.doctor_id, slot.start_time)
    notification_service.notify_booking(db, booking.id, NotificationType.CANCELLATION)
    return booking


def reschedule_booking(db: Session, patient: User, booking_id: int, new_slot_id: int) -> Booking:
    """Move a booking to another slot of the same doctor in a single transaction.

    Either everything happens (old booking cancelled, old slot freed, new booking
    created, new slot taken) or nothing does, so the patient never ends up with
    zero or two bookings.
    """
    try:
        lock_patient(db, patient)
        lock_doctor_for_booking(db, find_slot_doctor_id(db, new_slot_id))
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
        ensure_patient_can_book(db, patient, new_slot, replacing_booking_id=old_booking.id)
    except Exception:
        db.rollback()
        raise

    old_booking.status = BookingStatus.RESCHEDULED.value
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
    notification_service.notify_booking(db, new_booking.id, NotificationType.CONFIRMATION)
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
            .where(Booking.status.not_in([BookingStatus.CANCELLED.value, BookingStatus.RESCHEDULED.value]))
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


def cancel_bookings_by_clinic(db: Session, bookings: list[Booking]) -> list[int]:
    """Cancel bookings on the clinic's side, inside the caller's transaction.

    Locks the bookings, then their slots, each in id order (steps 3 and 4 of the
    lock order). The slots become blocked, because the doctor is not available
    then. Does not commit; returns the ids of the bookings it cancelled.
    """
    booking_ids = sorted(booking.id for booking in bookings)
    if not booking_ids:
        return []
    locked_bookings = list(
        db.scalars(select(Booking).where(Booking.id.in_(booking_ids)).order_by(Booking.id).with_for_update())
    )
    active = [booking for booking in locked_bookings if booking.status == BookingStatus.CONFIRMED.value]
    slot_ids = sorted(booking.slot_id for booking in active)
    slots = {
        slot.id: slot
        for slot in db.scalars(select(Slot).where(Slot.id.in_(slot_ids)).order_by(Slot.id).with_for_update())
    }
    cancelled_at = now_utc()
    for booking in active:
        booking.status = BookingStatus.CANCELLED.value
        booking.cancelled_at = cancelled_at
        booking.cancelled_by = CancelledBy.CLINIC.value
        slots[booking.slot_id].status = SlotStatus.BLOCKED.value
    return [booking.id for booking in active]


def future_confirmed_bookings(db: Session, doctor_ids: list[int]) -> list[Booking]:
    """Confirmed bookings that have not started yet, for the given doctors."""
    if not doctor_ids:
        return []
    query = (
        select(Booking)
        .join(Booking.slot)
        .where(Slot.doctor_id.in_(doctor_ids))
        .where(Booking.status == BookingStatus.CONFIRMED.value)
        .where(Slot.start_time > now_utc())
    )
    return list(db.scalars(query))


def notify_clinic_cancellations(db: Session, booking_ids: list[int]) -> None:
    """After the commit: tell each patient their appointment was cancelled."""
    for booking_id in booking_ids:
        BOOKINGS_CANCELLED.inc()
        notification_service.notify_booking(db, booking_id, NotificationType.CANCELLATION)


def cancel_appointment_by_doctor(db: Session, doctor: Doctor, booking_id: int) -> Booking:
    """The doctor cancels one upcoming appointment. The slot is blocked and the patient is emailed."""
    try:
        booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
        if booking is None or booking.slot.doctor_id != doctor.id:
            raise NotFoundError("BOOKING_NOT_FOUND", "Appointment not found.")
        if booking.status != BookingStatus.CONFIRMED.value:
            raise ConflictError("BOOKING_NOT_ACTIVE", "Only confirmed appointments can be cancelled.")
        if booking.slot.start_time <= now_utc():
            raise BusinessRuleError("APPOINTMENT_STARTED", "This appointment has already started.")
        cancelled_ids = cancel_bookings_by_clinic(db, [booking])
    except Exception:
        db.rollback()
        raise
    db.commit()
    cache_service.invalidate_slot_day(booking.slot.doctor_id, booking.slot.start_time)
    notify_clinic_cancellations(db, cancelled_ids)
    return booking
