from typing import Any

from celery import Celery, signals
from celery.schedules import crontab

from app.core.config import get_settings
from app.core.logging_config import setup_logging

settings = get_settings()

celery_app = Celery("medislot", broker=settings.celery_broker_url, include=["app.workers.tasks"])

celery_app.conf.update(
    timezone=settings.clinic_timezone,
    enable_utc=True,
    # A task is only removed from the queue once it has finished, so a worker
    # crash in the middle of sending an email does not lose the email.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "generate-slots-nightly": {
            "task": "app.workers.tasks.generate_upcoming_slots",
            "schedule": crontab(hour=0, minute=30),
        },
        "send-reminders": {
            "task": "app.workers.tasks.send_due_reminders",
            "schedule": crontab(minute="*/15"),
        },
        "delete-old-idempotency-keys": {
            "task": "app.workers.tasks.delete_expired_idempotency_keys",
            "schedule": crontab(minute=5),
        },
    },
)


@signals.setup_logging.connect
def use_json_logging(**kwargs: Any) -> None:
    """Make the worker and beat log in the same JSON format as the API."""
    setup_logging(settings.log_level)
