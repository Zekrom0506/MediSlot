from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Slot, WeeklySchedule
from app.services import slot_service
from tests.factories import add_schedule, future_date, make_doctor


def schedule_block(day_of_week: int, start: time, end: time) -> WeeklySchedule:
    return WeeklySchedule(doctor_id=1, day_of_week=day_of_week, start_time=start, end_time=end)


def count_slots(db: Session, doctor_id: int) -> int:
    return db.scalar(select(func.count(Slot.id)).where(Slot.doctor_id == doctor_id))


def test_build_slot_times_splits_block_and_converts_to_utc() -> None:
    monday = future_date(14)
    while monday.weekday() != 0:
        monday = monday + timedelta(days=1)
    entries = [schedule_block(0, time(9, 0), time(10, 0))]

    slot_times = slot_service.build_slot_times(entries, monday, 20)

    assert len(slot_times) == 3
    first_start, first_end = slot_times[0]
    # 09:00 in India (UTC+05:30) is 03:30 UTC.
    assert first_start == datetime.combine(monday, time(3, 30), tzinfo=UTC)
    assert first_end - first_start == timedelta(minutes=20)


def test_build_slot_times_drops_leftover_shorter_than_one_appointment() -> None:
    day = future_date(3)
    entries = [schedule_block(day.weekday(), time(9, 0), time(10, 0))]
    assert len(slot_service.build_slot_times(entries, day, 25)) == 2


def test_build_slot_times_ignores_other_weekdays() -> None:
    day = future_date(3)
    other_weekday = (day.weekday() + 1) % 7
    entries = [schedule_block(other_weekday, time(9, 0), time(10, 0))]
    assert slot_service.build_slot_times(entries, day, 15) == []


def test_generation_creates_slots_for_every_scheduled_day(db: Session) -> None:
    doctor = make_doctor(db, appointment_length_minutes=30)
    for day_of_week in range(7):
        add_schedule(db, doctor, day_of_week, time(9, 0), time(11, 0))

    created = slot_service.generate_slots_for_doctor(db, doctor, future_date(1), number_of_days=14)

    assert created == 14 * 4
    assert count_slots(db, doctor.id) == 56


def test_generation_twice_never_creates_duplicates(db: Session) -> None:
    doctor = make_doctor(db)
    add_schedule(db, doctor, future_date(2).weekday())

    first_run = slot_service.generate_slots_for_doctor(db, doctor, future_date(1), number_of_days=7)
    second_run = slot_service.generate_slots_for_doctor(db, doctor, future_date(1), number_of_days=7)

    assert first_run == 6
    assert second_run == 0
    assert count_slots(db, doctor.id) == 6


def test_generation_skips_times_in_the_past(db: Session) -> None:
    doctor = make_doctor(db)
    yesterday = future_date(-1)
    add_schedule(db, doctor, yesterday.weekday())

    created = slot_service.generate_slots_for_doctor(db, doctor, yesterday, number_of_days=1)
    assert created == 0


def test_generation_without_schedule_creates_nothing(db: Session) -> None:
    doctor = make_doctor(db)
    assert slot_service.generate_slots_for_doctor(db, doctor) == 0


def test_generate_for_all_doctors_skips_inactive_doctors(db: Session) -> None:
    active_doctor = make_doctor(db)
    inactive_doctor = make_doctor(db, clinic=active_doctor.clinic)
    inactive_doctor.is_active = False
    db.commit()
    for doctor in (active_doctor, inactive_doctor):
        for day_of_week in range(7):
            add_schedule(db, doctor, day_of_week)

    total = slot_service.generate_slots_for_all_doctors(db)

    assert total == count_slots(db, active_doctor.id)
    assert total > 0
    assert count_slots(db, inactive_doctor.id) == 0
