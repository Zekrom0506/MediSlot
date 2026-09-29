import logging

from celery import Task

from app.core.database import SessionLocal
from app.services import idempotency_service, notification_service, slot_service
from app.services.email_sender import EmailSender
from app.services.sms_sender import get_sms_sender
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

MAX_DELIVERY_RETRIES = 3
FIRST_RETRY_DELAY_SECONDS = 30


def retry_delay_seconds(retry_number: int) -> int:
    """Exponential backoff: 30s, 60s, 120s, ..."""
    return FIRST_RETRY_DELAY_SECONDS * (2**retry_number)


@celery_app.task(bind=True, max_retries=MAX_DELIVERY_RETRIES)
def send_notification(self: Task, notification_id: int) -> None:
    """Deliver one notification, retrying with growing delays if it fails."""
    with SessionLocal() as db:
        try:
            notification_service.deliver_notification(db, notification_id, EmailSender(), get_sms_sender())
        except Exception as error:
            if self.request.retries >= MAX_DELIVERY_RETRIES:
                notification_service.mark_failed(db, notification_id)
                logger.error("Notification failed for good", extra={"notification_id": notification_id})
                return
            raise self.retry(exc=error, countdown=retry_delay_seconds(self.request.retries))


@celery_app.task
def send_due_reminders() -> int:
    """Queue reminders for appointments in the next 24 hours."""
    with SessionLocal() as db:
        queued = notification_service.queue_due_reminders(db)
    logger.info("Reminders queued", extra={"count": queued})
    return queued


@celery_app.task
def generate_upcoming_slots() -> int:
    """Nightly: make sure every doctor has slots for the next 14 days."""
    with SessionLocal() as db:
        created = slot_service.generate_slots_for_all_doctors(db)
    logger.info("Slots generated", extra={"count": created})
    return created


@celery_app.task
def delete_expired_idempotency_keys() -> int:
    """Hourly: drop idempotency keys older than 24 hours."""
    with SessionLocal() as db:
        deleted = idempotency_service.delete_expired_keys(db)
    logger.info("Idempotency keys deleted", extra={"count": deleted})
    return deleted
