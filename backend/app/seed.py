"""Fill the database with demo data.

Run with:  python -m app.seed
Running it twice is safe: it stops early if the demo admin already exists.
"""

import logging
import random
from datetime import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Clinic, Doctor, User, WeeklySchedule
from app.models.enums import UserRole

logger = logging.getLogger(__name__)

DEMO_ADMIN_EMAIL = "admin@medislot.dev"
DEMO_DOCTOR_EMAIL = "doctor@medislot.dev"
DEMO_PATIENT_EMAIL = "patient@medislot.dev"
DEMO_PASSWORD = "Demo@1234"

CLINICS = [
    ("MediSlot Indiranagar", "12 CMH Road, Indiranagar", "Bengaluru"),
    ("MediSlot Andheri", "45 Link Road, Andheri West", "Mumbai"),
    ("MediSlot Saket", "8 Press Enclave Marg, Saket", "Delhi"),
]

# (name, specialty, years of experience, fee, appointment length in minutes)
DOCTORS = [
    ("Dr. Ananya Rao", "Cardiology", 14, 900, 20),
    ("Dr. Vikram Shetty", "Orthopedics", 11, 800, 20),
    ("Dr. Meera Iyer", "Dermatology", 8, 600, 15),
    ("Dr. Rahul Mehta", "General Medicine", 6, 400, 15),
    ("Dr. Sana Qureshi", "Pediatrics", 9, 500, 15),
    ("Dr. Arjun Kapoor", "Cardiology", 18, 1200, 30),
    ("Dr. Kavya Nair", "ENT", 7, 550, 15),
    ("Dr. Rohan Desai", "General Medicine", 4, 350, 15),
    ("Dr. Priya Sharma", "Gynecology", 12, 850, 20),
    ("Dr. Imran Khan", "Neurology", 15, 1100, 30),
]

FIRST_NAMES = ["Aarav", "Diya", "Kabir", "Isha", "Vivaan", "Anika", "Aditya", "Saanvi", "Reyansh", "Myra"]
LAST_NAMES = ["Gupta", "Reddy", "Joshi", "Patel", "Singh"]


def create_user(session: Session, full_name: str, email: str, role: UserRole, password_hash: str) -> User:
    """Add a user row and return it (not yet committed)."""
    user = User(
        full_name=full_name,
        email=email,
        hashed_password=password_hash,
        role=role.value,
        phone_number=f"+9198{random.randint(10000000, 99999999)}",
    )
    session.add(user)
    return user


def create_clinics(session: Session) -> list[Clinic]:
    """Create the three demo clinics."""
    clinics = []
    for name, address, city in CLINICS:
        clinic = Clinic(name=name, address=address, city=city)
        session.add(clinic)
        clinics.append(clinic)
    session.flush()
    return clinics


def create_doctors(session: Session, clinics: list[Clinic], password_hash: str) -> list[Doctor]:
    """Create ten doctors spread over the clinics. The first one gets the demo login."""
    doctors = []
    for index, (name, specialty, experience, fee, length) in enumerate(DOCTORS):
        if index == 0:
            email = DEMO_DOCTOR_EMAIL
        else:
            email = f"doctor{index + 1}@medislot.dev"
        user = create_user(session, name, email, UserRole.DOCTOR, password_hash)
        session.flush()
        doctor = Doctor(
            user_id=user.id,
            clinic_id=clinics[index % len(clinics)].id,
            specialty=specialty,
            years_of_experience=experience,
            consultation_fee=Decimal(fee),
            appointment_length_minutes=length,
        )
        session.add(doctor)
        doctors.append(doctor)
    session.flush()
    return doctors


def create_weekly_schedules(session: Session, doctors: list[Doctor]) -> None:
    """Give every doctor a Monday-to-Saturday morning shift and some evening shifts."""
    for index, doctor in enumerate(doctors):
        for day_of_week in range(0, 6):
            session.add(
                WeeklySchedule(
                    doctor_id=doctor.id,
                    day_of_week=day_of_week,
                    start_time=time(9, 0),
                    end_time=time(13, 0),
                )
            )
            if index % 2 == 0 and day_of_week in (1, 3):
                session.add(
                    WeeklySchedule(
                        doctor_id=doctor.id,
                        day_of_week=day_of_week,
                        start_time=time(17, 0),
                        end_time=time(20, 0),
                    )
                )
    session.flush()


def create_patients(session: Session, password_hash: str) -> list[User]:
    """Create fifty patients. The first one gets the demo login."""
    patients = [create_user(session, "Demo Patient", DEMO_PATIENT_EMAIL, UserRole.PATIENT, password_hash)]
    for number in range(1, 50):
        first_name = FIRST_NAMES[number % len(FIRST_NAMES)]
        last_name = LAST_NAMES[number % len(LAST_NAMES)]
        email = f"patient{number}@medislot.dev"
        patients.append(create_user(session, f"{first_name} {last_name}", email, UserRole.PATIENT, password_hash))
    session.flush()
    return patients


def seed(session: Session) -> bool:
    """Insert all demo data. Returns False if the data was already there."""
    already_seeded = session.scalar(select(User).where(User.email == DEMO_ADMIN_EMAIL))
    if already_seeded is not None:
        return False

    random.seed(42)
    # Hashing once and reusing it keeps seeding fast; bcrypt is slow on purpose.
    password_hash = hash_password(DEMO_PASSWORD)

    create_user(session, "Demo Admin", DEMO_ADMIN_EMAIL, UserRole.ADMIN, password_hash)
    clinics = create_clinics(session)
    doctors = create_doctors(session, clinics, password_hash)
    create_weekly_schedules(session, doctors)
    create_patients(session, password_hash)
    session.commit()
    return True


def main() -> None:
    """Entry point for `python -m app.seed`."""
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as session:
        created = seed(session)
    if created:
        logger.info("Demo data created. Password for every demo account: %s", DEMO_PASSWORD)
    else:
        logger.info("Demo data already exists, nothing to do.")


if __name__ == "__main__":
    main()
