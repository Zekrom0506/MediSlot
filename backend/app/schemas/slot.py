from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, field_validator

from app.core.timezones import today_local


def reject_past_date(value: date) -> date:
    """Shared check: dates in the past are not allowed."""
    if value < today_local():
        raise ValueError("date cannot be in the past")
    return value


# Use as a type for query parameters: a date that is today or later.
NotPastDate = Annotated[date, AfterValidator(reject_past_date)]


class SlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime
    status: str


class BlockDayRequest(BaseModel):
    date: date

    @field_validator("date")
    @classmethod
    def check_not_in_past(cls, value: date) -> date:
        return reject_past_date(value)


class BlockDayResponse(BaseModel):
    blocked_count: int
    # Booked slots are left alone; the doctor has to handle those appointments first.
    booked_count: int


class SlotGenerationResponse(BaseModel):
    created_count: int
