from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

# Everything is stored in UTC; this zone is only used to interpret "a day"
# and to show times to people in India.
CLINIC_TIMEZONE = ZoneInfo(get_settings().clinic_timezone)


def now_utc() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def today_local() -> date:
    """Today's date in the clinic timezone."""
    return datetime.now(CLINIC_TIMEZONE).date()


def local_to_utc(local_date: date, local_time: time) -> datetime:
    """Combine a clinic-local date and time into a UTC datetime."""
    local_datetime = datetime.combine(local_date, local_time, tzinfo=CLINIC_TIMEZONE)
    return local_datetime.astimezone(UTC)


def to_local(moment: datetime) -> datetime:
    """Convert a UTC datetime to clinic-local time for display."""
    return moment.astimezone(CLINIC_TIMEZONE)


def local_day_bounds_utc(local_date: date) -> tuple[datetime, datetime]:
    """Return the UTC start and end of a clinic-local calendar day."""
    day_start = local_to_utc(local_date, time(0, 0))
    day_end = local_to_utc(local_date + timedelta(days=1), time(0, 0))
    return day_start, day_end
