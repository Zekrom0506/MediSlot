from prometheus_client import Counter

# Business metrics, on top of the HTTP metrics the instrumentator records.
BOOKINGS_CREATED = Counter("medislot_bookings_created_total", "Bookings successfully created")
BOOKING_CONFLICTS = Counter(
    "medislot_booking_conflicts_total", "Booking attempts that lost the race for a slot"
)
BOOKINGS_CANCELLED = Counter("medislot_bookings_cancelled_total", "Bookings cancelled by patients")
