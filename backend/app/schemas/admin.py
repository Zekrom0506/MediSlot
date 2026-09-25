from datetime import date

from pydantic import BaseModel


class DailyBookingCount(BaseModel):
    date: date
    count: int


class BusyDoctor(BaseModel):
    doctor_id: int
    full_name: str
    specialty: str
    booking_count: int


class AdminStats(BaseModel):
    period_days: int
    total_bookings: int
    cancelled_bookings: int
    completed_bookings: int
    no_show_bookings: int
    # Rates are fractions between 0 and 1, rounded to 3 decimals.
    cancellation_rate: float
    no_show_rate: float
    bookings_per_day: list[DailyBookingCount]
    busiest_doctors: list[BusyDoctor]
