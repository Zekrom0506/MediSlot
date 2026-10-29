from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import Booking
from app.schemas.slot import SlotResponse


class BookingCreate(BaseModel):
    slot_id: int
    reason_for_visit: str | None = Field(default=None, max_length=500)


class RescheduleRequest(BaseModel):
    new_slot_id: int


class AppointmentOutcomeUpdate(BaseModel):
    status: Literal["completed", "no_show"]


class BookingDoctorSummary(BaseModel):
    id: int
    full_name: str
    specialty: str
    clinic_name: str
    clinic_address: str
    city: str


class BookingPatientSummary(BaseModel):
    id: int
    full_name: str
    phone_number: str | None


class BookingResponse(BaseModel):
    id: int
    status: str
    reason_for_visit: str | None
    created_at: datetime
    cancelled_at: datetime | None
    cancelled_by: str | None
    slot: SlotResponse
    doctor: BookingDoctorSummary

    @classmethod
    def from_booking(cls, booking: Booking) -> "BookingResponse":
        """Build the patient-facing view of a booking, including doctor and clinic details."""
        doctor = booking.slot.doctor
        return cls(
            id=booking.id,
            status=booking.status,
            reason_for_visit=booking.reason_for_visit,
            created_at=booking.created_at,
            cancelled_at=booking.cancelled_at,
            cancelled_by=booking.cancelled_by,
            slot=SlotResponse.model_validate(booking.slot),
            doctor=BookingDoctorSummary(
                id=doctor.id,
                full_name=doctor.user.full_name,
                specialty=doctor.specialty,
                clinic_name=doctor.clinic.name,
                clinic_address=doctor.clinic.address,
                city=doctor.clinic.city,
            ),
        )


class DoctorAppointmentResponse(BaseModel):
    id: int
    status: str
    reason_for_visit: str | None
    slot: SlotResponse
    patient: BookingPatientSummary

    @classmethod
    def from_booking(cls, booking: Booking) -> "DoctorAppointmentResponse":
        """Build the doctor-facing view of a booking, including the patient's contact."""
        return cls(
            id=booking.id,
            status=booking.status,
            reason_for_visit=booking.reason_for_visit,
            slot=SlotResponse.model_validate(booking.slot),
            patient=BookingPatientSummary(
                id=booking.patient.id,
                full_name=booking.patient.full_name,
                phone_number=booking.patient.phone_number,
            ),
        )
