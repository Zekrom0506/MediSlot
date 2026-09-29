"""Creating and delivering booking notifications.

The API only creates notification rows and puts their ids on the Celery queue,
so a slow or broken mail server never slows down booking. A worker picks the
ids up and calls deliver_notification().
"""

import logging
from datetime import timedelta

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.timezones import now_utc, to_local
from app.models import Booking, Notification, Slot
from app.models.enums import BookingStatus, NotificationChannel, NotificationStatus, NotificationType
from app.services.email_sender import EmailSender
from app.services.sms_sender import SmsSender

logger = logging.getLogger(__name__)


def load_booking(db: Session, booking_id: int) -> Booking | None:
    """Booking with patient, slot, doctor and clinic loaded."""
    query = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(joinedload(Booking.patient))
        .options(joinedload(Booking.slot).joinedload(Slot.doctor))
    )
    return db.scalar(query)


def create_notifications(db: Session, booking: Booking, notification_type: NotificationType) -> list[int]:
    """Add one email row, and one SMS row if the patient has a phone. Returns new ids.

    ON CONFLICT DO NOTHING means asking twice for the same notification is harmless.
    """
    channels = [NotificationChannel.EMAIL]
    if booking.patient.phone_number:
        channels.append(NotificationChannel.SMS)

    created_ids = []
    for channel in channels:
        statement = (
            insert(Notification)
            .values(
                user_id=booking.patient_id,
                booking_id=booking.id,
                type=notification_type.value,
                channel=channel.value,
                status=NotificationStatus.PENDING.value,
            )
            .on_conflict_do_nothing(constraint="uq_notifications_booking_type_channel")
            .returning(Notification.id)
        )
        new_id = db.scalar(statement)
        if new_id is not None:
            created_ids.append(new_id)
    db.commit()
    return created_ids


def enqueue_notification(notification_id: int) -> None:
    """Put a notification on the Celery queue."""
    # Imported here to avoid a circular import: the tasks module imports this one.
    from app.workers.tasks import send_notification

    send_notification.delay(notification_id)


def notify_booking(db: Session, booking_id: int, notification_type: NotificationType) -> None:
    """Create and queue notifications for a booking. Never raises.

    The booking is already committed at this point; a notification problem
    must not turn a successful booking into an error for the patient.
    """
    try:
        booking = load_booking(db, booking_id)
        if booking is None:
            return
        for notification_id in create_notifications(db, booking, notification_type):
            enqueue_notification(notification_id)
    except Exception:
        db.rollback()
        logger.exception("Could not queue notification", extra={"booking_id": booking_id})


def build_message(notification: Notification, booking: Booking) -> tuple[str, str]:
    """Subject and body text for a notification, with times shown in clinic time."""
    doctor = booking.slot.doctor
    local_start = to_local(booking.slot.start_time)
    when = local_start.strftime("%A, %d %B %Y at %I:%M %p")
    where = f"{doctor.clinic.name}, {doctor.clinic.address}, {doctor.clinic.city}"
    greeting = f"Hello {booking.patient.full_name},"

    if notification.type == NotificationType.CONFIRMATION.value:
        subject = "Your MediSlot appointment is confirmed"
        line = f"Your appointment with {doctor.user.full_name} is confirmed for {when}."
    elif notification.type == NotificationType.CANCELLATION.value:
        subject = "Your MediSlot appointment was cancelled"
        line = f"Your appointment with {doctor.user.full_name} on {when} has been cancelled."
    else:
        subject = "Reminder: your MediSlot appointment is tomorrow"
        line = f"This is a reminder of your appointment with {doctor.user.full_name} on {when}."

    body = f"{greeting}\n\n{line}\nClinic: {where}\nBooking reference: #{booking.id}\n\nMediSlot"
    return subject, body


def deliver_notification(
    db: Session, notification_id: int, email_sender: EmailSender, sms_sender: SmsSender
) -> None:
    """Send one notification and record the attempt. Re-raises on failure so Celery can retry."""
    notification = db.get(Notification, notification_id)
    if notification is None or notification.status == NotificationStatus.SENT.value:
        return
    booking = load_booking(db, notification.booking_id)

    notification.attempts += 1
    try:
        subject, body = build_message(notification, booking)
        if notification.channel == NotificationChannel.EMAIL.value:
            email_sender.send(booking.patient.email, subject, body)
        else:
            sms_sender.send(booking.patient.phone_number, f"{subject}. {body}")
    except Exception as error:
        notification.last_error = str(error)[:1000]
        db.commit()
        raise

    notification.status = NotificationStatus.SENT.value
    notification.sent_at = now_utc()
    notification.last_error = None
    db.commit()


def mark_failed(db: Session, notification_id: int) -> None:
    """Give up on a notification after the last retry."""
    notification = db.get(Notification, notification_id)
    if notification is not None:
        notification.status = NotificationStatus.FAILED.value
        db.commit()


def bookings_needing_reminder(db: Session) -> list[int]:
    """Confirmed bookings starting within the reminder window that have no reminder yet."""
    current_time = now_utc()
    window_end = current_time + timedelta(hours=get_settings().reminder_hours_before)
    already_reminded = exists().where(
        Notification.booking_id == Booking.id,
        Notification.type == NotificationType.REMINDER.value,
    )
    query = (
        select(Booking.id)
        .join(Booking.slot)
        .where(Booking.status == BookingStatus.CONFIRMED.value)
        .where(Slot.start_time > current_time)
        .where(Slot.start_time <= window_end)
        .where(~already_reminded)
    )
    return list(db.scalars(query))


def queue_due_reminders(db: Session) -> int:
    """Create and queue reminders for every booking that needs one."""
    booking_ids = bookings_needing_reminder(db)
    for booking_id in booking_ids:
        notify_booking(db, booking_id, NotificationType.REMINDER)
    return len(booking_ids)
