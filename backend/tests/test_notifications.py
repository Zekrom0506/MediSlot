from datetime import timedelta
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification
from app.models.enums import NotificationStatus
from app.services import email_sender as email_sender_module
from app.services import notification_service
from app.services.email_sender import EmailSender
from app.workers import tasks
from tests.factories import auth_headers, make_doctor, make_slot, make_user


class RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to_address: str, subject: str, body: str) -> None:
        self.sent.append((to_address, subject, body))


class BrokenEmailSender:
    def send(self, to_address: str, subject: str, body: str) -> None:
        raise ConnectionError("mail server unreachable")


def book(client: TestClient, db: Session, patient=None, starts_in: timedelta = timedelta(days=2)) -> int:
    if patient is None:
        patient = make_user(db)
    slot = make_slot(db, make_doctor(db, full_name="Dr. Mail"), starts_in=starts_in)
    response = client.post("/api/bookings", json={"slot_id": slot.id}, headers=auth_headers(patient))
    assert response.status_code == 201
    return response.json()["id"]


def notifications(db: Session) -> list[Notification]:
    db.expire_all()
    return list(db.scalars(select(Notification).order_by(Notification.id)))


def test_booking_queues_one_confirmation_email(
    client: TestClient, db: Session, queued_notifications: list[int]
) -> None:
    book(client, db)

    rows = notifications(db)
    assert [(row.type, row.status) for row in rows] == [("confirmation", "pending")]
    assert queued_notifications == [rows[0].id]


def test_cancellation_is_notified(client: TestClient, db: Session) -> None:
    patient = make_user(db)
    booking_id = book(client, db, patient)
    client.post(f"/api/bookings/{booking_id}/cancel", headers=auth_headers(patient))

    types = [row.type for row in notifications(db)]
    assert types.count("cancellation") == 1


def test_queue_failure_does_not_break_booking(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broker_down(notification_id: int) -> None:
        raise ConnectionError("broker down")

    monkeypatch.setattr(notification_service, "enqueue_notification", broker_down)
    book(client, db)


def test_deliver_sends_email_with_clinic_time(client: TestClient, db: Session) -> None:
    book(client, db)
    email_row = notifications(db)[0]
    sender = RecordingEmailSender()

    notification_service.deliver_notification(db, email_row.id, sender)

    to_address, subject, body = sender.sent[0]
    assert subject == "Your MediSlot appointment is confirmed"
    assert "Dr. Mail" in body
    assert ("AM" in body) or ("PM" in body)
    delivered = notifications(db)[0]
    assert delivered.status == NotificationStatus.SENT.value
    assert delivered.attempts == 1
    assert delivered.sent_at is not None

    # Delivering an already-sent notification again does nothing.
    notification_service.deliver_notification(db, email_row.id, sender)
    assert len(sender.sent) == 1


def test_deliver_records_failed_attempt(client: TestClient, db: Session) -> None:
    book(client, db)
    email_row = notifications(db)[0]

    with pytest.raises(ConnectionError):
        notification_service.deliver_notification(db, email_row.id, BrokenEmailSender())

    failed = notifications(db)[0]
    assert failed.attempts == 1
    assert failed.status == NotificationStatus.PENDING.value
    assert failed.last_error == "mail server unreachable"


def test_task_retries_three_times_then_marks_failed(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    book(client, db)
    email_row = notifications(db)[0]
    monkeypatch.setattr(tasks, "EmailSender", BrokenEmailSender)

    tasks.send_notification.apply(args=[email_row.id])

    final = notifications(db)[0]
    assert final.attempts == 4
    assert final.status == NotificationStatus.FAILED.value


def test_task_sends_email_through_sender(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    book(client, db)
    email_row = notifications(db)[0]
    sender = RecordingEmailSender()
    monkeypatch.setattr(tasks, "EmailSender", lambda: sender)

    tasks.send_notification.apply(args=[email_row.id])

    assert notifications(db)[0].status == NotificationStatus.SENT.value
    assert len(sender.sent) == 1


def test_retry_delays_grow_exponentially() -> None:
    assert [tasks.retry_delay_seconds(number) for number in range(3)] == [30, 60, 120]


def test_reminders_only_for_bookings_in_the_next_24_hours(client: TestClient, db: Session) -> None:
    soon_booking = book(client, db, starts_in=timedelta(hours=5))
    book(client, db, starts_in=timedelta(days=3))

    first_run = tasks.send_due_reminders()
    second_run = tasks.send_due_reminders()

    assert first_run == 1
    assert second_run == 0
    reminders = [row for row in notifications(db) if row.type == "reminder"]
    assert {row.booking_id for row in reminders} == {soon_booking}


def test_reminder_message_text(client: TestClient, db: Session) -> None:
    book(client, db, starts_in=timedelta(hours=5))
    tasks.send_due_reminders()
    reminder = [row for row in notifications(db) if row.type == "reminder"][0]
    sender = RecordingEmailSender()

    notification_service.deliver_notification(db, reminder.id, sender)

    assert sender.sent[0][1].startswith("Reminder")


def test_email_sender_uses_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_messages = []

    class FakeSmtp:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            self.host = host

        def __enter__(self) -> "FakeSmtp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def send_message(self, message: EmailMessage) -> None:
            sent_messages.append(message)

    monkeypatch.setattr(email_sender_module.smtplib, "SMTP", FakeSmtp)
    EmailSender().send("asha@example.com", "Hello", "Body text")

    assert sent_messages[0]["To"] == "asha@example.com"
    assert sent_messages[0]["Subject"] == "Hello"


def test_maintenance_tasks_run(db: Session) -> None:
    assert tasks.generate_upcoming_slots() == 0
    assert tasks.delete_expired_idempotency_keys() == 0
