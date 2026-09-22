from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, enum_column
from app.models.enums import BookingStatus
from app.models.slot import Slot
from app.models.user import User


class Booking(Base):
    """A patient's appointment in a slot."""

    __tablename__ = "bookings"
    __table_args__ = (
        # Safety net against double booking: even if the application logic had a bug,
        # Postgres refuses a second *confirmed* booking for the same slot.
        # Cancelled bookings are excluded, so a freed slot can be booked again.
        Index(
            "uq_bookings_one_confirmed_per_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), index=True)
    status: Mapped[str] = mapped_column(enum_column(BookingStatus), default=BookingStatus.CONFIRMED.value)
    reason_for_visit: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    slot: Mapped[Slot] = relationship()
    patient: Mapped[User] = relationship()
