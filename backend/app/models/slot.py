from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, enum_column
from app.models.doctor import Doctor
from app.models.enums import SlotStatus


class Slot(Base):
    """A single bookable time window for one doctor."""

    __tablename__ = "slots"
    __table_args__ = (
        # A doctor can never have two live slots whose times overlap, even if the
        # visit length or weekly schedule changes. This also lets the nightly
        # generator run any number of times: ON CONFLICT DO NOTHING skips slots
        # that already exist or would overlap one. Needs the btree_gist extension.
        ExcludeConstraint(
            ("doctor_id", "="),
            (text("tstzrange(start_time, end_time)"), "&&"),
            name="ex_slots_no_overlap",
            using="gist",
            where=text("status <> 'retired'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(enum_column(SlotStatus), default=SlotStatus.AVAILABLE.value)

    # Loaded on demand (not joined) so that "SELECT ... FOR UPDATE" on slots
    # only ever locks the slot row itself.
    doctor: Mapped[Doctor] = relationship()
