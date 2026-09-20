"""Small helpers to create test data directly in the database."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.core.timezones import now_utc, today_local
from app.models import Clinic, Doctor, Slot, User, WeeklySchedule
from app.models.enums import SlotStatus, UserRole

TEST_PASSWORD = "Password123!"
# Hashed once: bcrypt is deliberately slow and tests create many users.
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


def make_user(
    db: Session,
    role: UserRole = UserRole.PATIENT,
    email: str | None = None,
    full_name: str = "Test User",
) -> User:
    """Create and commit a user with the shared test password."""
    if email is None:
        count = db.query(User).count()
        email = f"{role.value}{count + 1}@example.com"
    user = User(
        full_name=full_name,
        email=email,
        hashed_password=TEST_PASSWORD_HASH,
        role=role.value,
        phone_number="+919876543210",
    )
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    """Authorization header with a valid access token for the user."""
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


def make_clinic(db: Session, city: str = "Bengaluru", name: str = "Test Clinic") -> Clinic:
    """Create and commit a clinic."""
    clinic = Clinic(name=name, address="1 Test Road", city=city)
    db.add(clinic)
    db.commit()
    return clinic


def make_doctor(
    db: Session,
    clinic: Clinic | None = None,
    specialty: str = "Cardiology",
    appointment_length_minutes: int = 30,
    full_name: str = "Dr. Test",
) -> Doctor:
    """Create a doctor user and profile."""
    if clinic is None:
        clinic = make_clinic(db)
    user = make_user(db, role=UserRole.DOCTOR, full_name=full_name)
    doctor = Doctor(
        user_id=user.id,
        clinic_id=clinic.id,
        specialty=specialty,
        years_of_experience=10,
        consultation_fee=Decimal("500.00"),
        appointment_length_minutes=appointment_length_minutes,
    )
    db.add(doctor)
    db.commit()
    return doctor


def add_schedule(
    db: Session, doctor: Doctor, day_of_week: int, start: time = time(9, 0), end: time = time(12, 0)
) -> WeeklySchedule:
    """Add one weekly schedule block for a doctor."""
    entry = WeeklySchedule(doctor_id=doctor.id, day_of_week=day_of_week, start_time=start, end_time=end)
    db.add(entry)
    db.commit()
    return entry


def make_slot(
    db: Session,
    doctor: Doctor,
    starts_in: timedelta = timedelta(days=2),
    length_minutes: int = 30,
    status: SlotStatus = SlotStatus.AVAILABLE,
) -> Slot:
    """Create a slot that starts a given amount of time from now."""
    start_time = now_utc().replace(microsecond=0) + starts_in
    return make_slot_at(db, doctor, start_time, length_minutes, status)


def make_slot_at(
    db: Session,
    doctor: Doctor,
    start_time: datetime,
    length_minutes: int = 30,
    status: SlotStatus = SlotStatus.AVAILABLE,
) -> Slot:
    """Create a slot at an exact UTC start time."""
    slot = Slot(
        doctor_id=doctor.id,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=length_minutes),
        status=status.value,
    )
    db.add(slot)
    db.commit()
    return slot


def future_date(days_ahead: int = 2) -> date:
    """A clinic-local date a few days from today."""
    return today_local() + timedelta(days=days_ahead)
