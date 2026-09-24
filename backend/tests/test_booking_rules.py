from datetime import UTC, datetime, timedelta

from app.services.booking_service import can_cancel

APPOINTMENT_START = datetime(2030, 1, 10, 10, 0, tzinfo=UTC)


def test_can_cancel_well_before_the_appointment() -> None:
    assert can_cancel(APPOINTMENT_START, APPOINTMENT_START - timedelta(days=1)) is True


def test_can_cancel_exactly_at_the_deadline() -> None:
    assert can_cancel(APPOINTMENT_START, APPOINTMENT_START - timedelta(hours=2)) is True


def test_cannot_cancel_inside_the_last_two_hours() -> None:
    assert can_cancel(APPOINTMENT_START, APPOINTMENT_START - timedelta(hours=1, minutes=59)) is False


def test_cannot_cancel_after_the_appointment_started() -> None:
    assert can_cancel(APPOINTMENT_START, APPOINTMENT_START + timedelta(minutes=5)) is False
