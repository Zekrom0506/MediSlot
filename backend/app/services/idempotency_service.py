"""Safe retries for booking.

The client sends a unique Idempotency-Key header with each booking attempt.
The first request with a key does the work and stores its response under that
key *in the same transaction* as the booking. Any later request with the same
key gets the stored response back instead of booking again.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError
from app.core.timezones import now_utc
from app.models import IdempotencyKey, User
from app.schemas.booking import BookingResponse
from app.services import booking_service, cache_service

KEY_LIFETIME = timedelta(hours=24)


class IdempotencyKeyReusedError(AppError):
    status_code = 422


def find_saved_response(db: Session, key: str) -> IdempotencyKey | None:
    """Look up a stored response by its key."""
    return db.scalar(select(IdempotencyKey).where(IdempotencyKey.key == key))


def check_same_request(saved: IdempotencyKey, user: User, slot_id: int) -> None:
    """A key may only be replayed by the same user for the same slot."""
    saved_slot_id = saved.response_body.get("slot", {}).get("id")
    if saved.user_id != user.id or saved_slot_id != slot_id:
        raise IdempotencyKeyReusedError(
            "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was already used for a different request."
        )


def book_with_idempotency_key(
    db: Session, patient: User, slot_id: int, reason_for_visit: str | None, key: str
) -> tuple[int, dict[str, Any], bool]:
    """Book once per key. Returns (status code, response body, was_replayed)."""
    saved = find_saved_response(db, key)
    if saved is not None:
        check_same_request(saved, patient, slot_id)
        return saved.response_status_code, saved.response_body, True

    try:
        booking = booking_service.reserve_slot(db, patient, slot_id, reason_for_visit)
        db.refresh(booking)
        response_body = BookingResponse.from_booking(booking).model_dump(mode="json")
        db.add(
            IdempotencyKey(
                key=key,
                user_id=patient.id,
                response_status_code=201,
                response_body=response_body,
            )
        )
        booking_service.commit_or_slot_taken(db)
    except ConflictError:
        # A duplicate request that arrived at the same moment waits on the slot
        # lock, then sees the slot as booked. By then the first request has
        # committed its key, so we can answer with the original response.
        db.rollback()
        saved = find_saved_response(db, key)
        if saved is None:
            raise
        check_same_request(saved, patient, slot_id)
        return saved.response_status_code, saved.response_body, True

    cache_service.invalidate_slot_day(booking.slot.doctor_id, booking.slot.start_time)
    return 201, response_body, False


def delete_expired_keys(db: Session) -> int:
    """Remove keys older than 24 hours. Returns how many were deleted."""
    cutoff = now_utc() - KEY_LIFETIME
    result = db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff))
    db.commit()
    return result.rowcount
