from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, enum_column
from app.models.enums import SlotStatus


class Slot(Base):
    """A single bookable time window for one doctor."""

    __tablename__ = "slots"
    # Lets the nightly generator run any number of times without creating duplicates.
    __table_args__ = (
        UniqueConstraint("doctor_id", "start_time", name="uq_slots_doctor_start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        enum_column(SlotStatus), default=SlotStatus.AVAILABLE.value
    )
