import enum


class UserRole(str, enum.Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"


class SlotStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"
    BLOCKED = "blocked"
    # No longer offered (e.g. the schedule or visit length changed) but kept because
    # an old booking points at it. Retired slots are hidden and never block new slots.
    RETIRED = "retired"


class BookingStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    # The patient moved to another slot; the replacement is a new confirmed booking.
    RESCHEDULED = "rescheduled"


class CancelledBy(str, enum.Enum):
    PATIENT = "patient"
    CLINIC = "clinic"


class NotificationType(str, enum.Enum):
    CONFIRMATION = "confirmation"
    CANCELLATION = "cancellation"
    REMINDER = "reminder"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
