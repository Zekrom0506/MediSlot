from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import Doctor
from app.schemas.clinic import ClinicResponse
from app.schemas.common import validate_phone_number


class DoctorCreate(BaseModel):
    """Admin creates the doctor's login and profile in one step."""

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone_number: str | None = None
    clinic_id: int
    specialty: str = Field(min_length=2, max_length=80)
    years_of_experience: int = Field(ge=0, le=70)
    consultation_fee: Decimal = Field(ge=0, le=100000, decimal_places=2)
    appointment_length_minutes: int = Field(default=15, ge=5, le=120)

    @field_validator("phone_number")
    @classmethod
    def check_phone_number(cls, value: str | None) -> str | None:
        return validate_phone_number(value)


class DoctorUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone_number: str | None = None
    clinic_id: int | None = None
    specialty: str | None = Field(default=None, min_length=2, max_length=80)
    years_of_experience: int | None = Field(default=None, ge=0, le=70)
    consultation_fee: Decimal | None = Field(default=None, ge=0, le=100000, decimal_places=2)
    appointment_length_minutes: int | None = Field(default=None, ge=5, le=120)
    is_active: bool | None = None

    @field_validator("phone_number")
    @classmethod
    def check_phone_number(cls, value: str | None) -> str | None:
        return validate_phone_number(value)


class DoctorResponse(BaseModel):
    id: int
    user_id: int
    full_name: str
    email: str
    specialty: str
    years_of_experience: int
    consultation_fee: Decimal
    appointment_length_minutes: int
    is_active: bool
    clinic: ClinicResponse

    @classmethod
    def from_doctor(cls, doctor: Doctor) -> "DoctorResponse":
        """Flatten the doctor and its linked user into one response."""
        return cls(
            id=doctor.id,
            user_id=doctor.user_id,
            full_name=doctor.user.full_name,
            email=doctor.user.email,
            specialty=doctor.specialty,
            years_of_experience=doctor.years_of_experience,
            consultation_fee=doctor.consultation_fee,
            appointment_length_minutes=doctor.appointment_length_minutes,
            is_active=doctor.is_active,
            clinic=ClinicResponse.model_validate(doctor.clinic),
        )


class DoctorSearchResult(DoctorResponse):
    # Only filled in when the search was for a specific date.
    available_slot_count: int | None = None


class SearchFilters(BaseModel):
    specialties: list[str]
    cities: list[str]
