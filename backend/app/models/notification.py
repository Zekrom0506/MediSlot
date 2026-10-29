from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, enum_column
from app.models.enums import NotificationStatus, NotificationType


class Notification(Base):
    """An email we need to send, and whether it went out."""

    __tablename__ = "notifications"
    # One notification of each kind per booking, so a reminder job that runs
    # twice cannot send the same reminder twice.
    __table_args__ = (UniqueConstraint("booking_id", "type", name="uq_notifications_booking_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), index=True)
    type: Mapped[str] = mapped_column(enum_column(NotificationType))
    status: Mapped[str] = mapped_column(
        enum_column(NotificationStatus), default=NotificationStatus.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
