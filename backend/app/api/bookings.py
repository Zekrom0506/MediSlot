from typing import Annotated, Literal

from fastapi import APIRouter, Header, status
from fastapi.responses import JSONResponse

from app.api.deps import DbSession, PatientUser, limit_booking_attempts
from app.schemas.booking import BookingCreate, BookingResponse, RescheduleRequest
from app.services import booking_service, idempotency_service

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


IdempotencyKeyHeader = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
]


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    request: BookingCreate,
    current_user: PatientUser,
    db: DbSession,
    idempotency_key: IdempotencyKeyHeader = None,
) -> BookingResponse | JSONResponse:
    """Book a slot. Returns 409 if someone else got it first.

    Send an Idempotency-Key header to make retries safe: repeating the request
    with the same key returns the first response instead of booking twice.
    A retry that is answered from the saved response does not count towards
    the booking rate limit, so a flaky connection cannot lock a patient out.
    """
    is_known_retry = (
        idempotency_key is not None
        and idempotency_service.find_saved_response(db, idempotency_key) is not None
    )
    if not is_known_retry:
        limit_booking_attempts(current_user)

    if idempotency_key is None:
        booking = booking_service.book_slot(db, current_user, request.slot_id, request.reason_for_visit)
        booking = booking_service.get_booking_for_patient(db, current_user, booking.id)
        return BookingResponse.from_booking(booking)

    status_code, body, was_replayed = idempotency_service.book_with_idempotency_key(
        db, current_user, request.slot_id, request.reason_for_visit, idempotency_key
    )
    headers = {}
    if was_replayed:
        headers["Idempotent-Replayed"] = "true"
    return JSONResponse(status_code=status_code, content=body, headers=headers)


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
