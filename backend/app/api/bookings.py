from typing import Literal

from fastapi import APIRouter, status

from app.api.deps import DbSession, PatientUser
from app.schemas.booking import BookingCreate, BookingResponse, RescheduleRequest
from app.services import booking_service

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(request: BookingCreate, current_user: PatientUser, db: DbSession) -> BookingResponse:
    """Book a slot. Returns 409 if someone else got it first."""
    booking = booking_service.book_slot(db, current_user, request.slot_id, request.reason_for_visit)
    booking = booking_service.get_booking_for_patient(db, current_user, booking.id)
    return BookingResponse.from_booking(booking)


@router.get("/me", response_model=list[BookingResponse])
def my_bookings(
    current_user: PatientUser, db: DbSession, scope: Literal["upcoming", "past"] = "upcoming"
) -> list[BookingResponse]:
    """The patient's upcoming appointments, or their history."""
    bookings = booking_service.list_patient_bookings(db, current_user, scope)
    return [BookingResponse.from_booking(booking) for booking in bookings]


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: int, current_user: PatientUser, db: DbSession) -> BookingResponse:
    """One of the patient's bookings."""
    booking = booking_service.get_booking_for_patient(db, current_user, booking_id)
    return BookingResponse.from_booking(booking)


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
def cancel_booking(booking_id: int, current_user: PatientUser, db: DbSession) -> BookingResponse:
    """Cancel a booking (allowed until 2 hours before it starts)."""
    booking_service.cancel_booking(db, current_user, booking_id)
    booking = booking_service.get_booking_for_patient(db, current_user, booking_id)
    return BookingResponse.from_booking(booking)


@router.post("/{booking_id}/reschedule", response_model=BookingResponse)
def reschedule_booking(
    booking_id: int, request: RescheduleRequest, current_user: PatientUser, db: DbSession
) -> BookingResponse:
    """Move a booking to another slot. Returns the new booking."""
    new_booking = booking_service.reschedule_booking(db, current_user, booking_id, request.new_slot_id)
    new_booking = booking_service.get_booking_for_patient(db, current_user, new_booking.id)
    return BookingResponse.from_booking(new_booking)
