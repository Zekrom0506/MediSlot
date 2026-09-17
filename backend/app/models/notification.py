from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, enum_column
from app.models.enums import NotificationChannel, NotificationStatus, NotificationType


class Notification(Base):
    """An email or SMS we need to send, and whether it went out."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(enum_column(NotificationType))
    channel: Mapped[str] = mapped_column(enum_column(NotificationChannel))
    status: Mapped[str] = mapped_column(
        enum_column(NotificationStatus), default=NotificationStatus.PENDING.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
