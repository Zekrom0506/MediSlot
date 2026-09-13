from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.clinic import Clinic
from app.models.user import User


class Doctor(Base):
    """Professional details of a doctor. Login details live in the linked user row."""

    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    specialty: Mapped[str] = mapped_column(String(80), index=True)
    years_of_experience: Mapped[int] = mapped_column(Integer)
    consultation_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    appointment_length_minutes: Mapped[int] = mapped_column(Integer, default=15)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    user: Mapped[User] = relationship(lazy="joined")
    clinic: Mapped[Clinic] = relationship(lazy="joined")
