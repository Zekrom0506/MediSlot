from datetime import time

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeeklySchedule(Base):
    """One recurring working block, e.g. every Monday 09:00 to 13:00 (clinic time)."""

    __tablename__ = "weekly_schedules"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_schedule_day_of_week"),
        CheckConstraint("start_time < end_time", name="ck_schedule_start_before_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    # 0 = Monday ... 6 = Sunday, same as Python's date.weekday()
    day_of_week: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
