from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.core.timezones import local_day_bounds_utc, now_utc
from app.models import Clinic, Doctor, Slot, User
from app.models.enums import SlotStatus, UserRole
from app.schemas.doctor import DoctorCreate, DoctorSearchResult, DoctorUpdate, SearchFilters
from app.services import auth_service, booking_service, cache_service, clinic_service, slot_service


def get_doctor(db: Session, doctor_id: int) -> Doctor:
    """Fetch any doctor (active or not) or raise a 404."""
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise NotFoundError("DOCTOR_NOT_FOUND", "Doctor not found.")
    return doctor


def get_active_doctor(db: Session, doctor_id: int) -> Doctor:
    """Fetch a doctor that patients are allowed to see and book."""
    doctor = get_doctor(db, doctor_id)
    if not doctor.is_active or not doctor.clinic.is_active:
        raise NotFoundError("DOCTOR_NOT_FOUND", "Doctor not found.")
    return doctor


def get_doctor_for_user(db: Session, user: User) -> Doctor:
    """Find the doctor profile that belongs to a logged-in doctor user."""
    doctor = db.scalar(select(Doctor).where(Doctor.user_id == user.id))
    if doctor is None:
        raise NotFoundError("DOCTOR_PROFILE_NOT_FOUND", "No doctor profile is linked to this account.")
    if not doctor.is_active:
        raise PermissionDeniedError("DOCTOR_INACTIVE", "This doctor profile has been deactivated.")
    return doctor


def list_doctors(db: Session) -> list[Doctor]:
    """All doctors for the admin screen."""
    return list(db.scalars(select(Doctor).order_by(Doctor.id)))


def create_doctor(db: Session, request: DoctorCreate) -> Doctor:
    """Create a doctor's user account and profile together, in one transaction."""
    if auth_service.find_user_by_email(db, request.email) is not None:
        raise ConflictError("EMAIL_ALREADY_REGISTERED", "An account with this email already exists.")

    clinic = clinic_service.get_clinic(db, request.clinic_id)
    if not clinic.is_active:
        raise BusinessRuleError("CLINIC_INACTIVE", "Doctors cannot be added to an inactive clinic.")

    user = User(
        full_name=request.full_name,
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
        role=UserRole.DOCTOR.value,
        phone_number=request.phone_number,
    )
    db.add(user)
    db.flush()

    doctor = Doctor(
        user_id=user.id,
        clinic_id=clinic.id,
        specialty=request.specialty.strip().title(),
        years_of_experience=request.years_of_experience,
        consultation_fee=request.consultation_fee,
        appointment_length_minutes=request.appointment_length_minutes,
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


def update_doctor(db: Session, doctor_id: int, request: DoctorUpdate) -> Doctor:
    """Update profile fields. Name and phone live on the user row.

    Turning is_active off goes through deactivate_doctor(), so upcoming
    appointments are cancelled and patients are told, however it is requested.
    A new visit length replaces the doctor's free future slots with new ones.
    """
    changes = request.model_dump(exclude_unset=True)
    is_active = changes.pop("is_active", None)
    if is_active is False:
        deactivate_doctor(db, doctor_id)

    doctor = get_doctor(db, doctor_id)
    if changes.get("clinic_id") is not None:
        clinic = clinic_service.get_clinic(db, changes["clinic_id"])
        if not clinic.is_active:
            raise BusinessRuleError("CLINIC_INACTIVE", "Doctors cannot be moved to an inactive clinic.")
    if "specialty" in changes and changes["specialty"] is not None:
        changes["specialty"] = changes["specialty"].strip().title()

    new_length = changes.get("appointment_length_minutes")
    length_changed = new_length is not None and new_length != doctor.appointment_length_minutes

    for field_name, value in changes.items():
        if field_name in ("full_name", "phone_number"):
            setattr(doctor.user, field_name, value)
        else:
            setattr(doctor, field_name, value)
    if is_active is True:
        doctor.is_active = True
    if length_changed:
        # Old-length free slots go; booked ones stay, and new slots are fitted around them.
        slot_service.retire_free_future_slots(db, doctor, keep=lambda slot: False)
    db.commit()

    if length_changed or is_active is True:
        cache_service.invalidate_doctor(doctor.id)
        slot_service.generate_slots_for_doctor(db, doctor)
    db.refresh(doctor)
    return doctor


def deactivate_doctor(db: Session, doctor_id: int) -> Doctor:
    """Hide a doctor and stop new bookings. Their upcoming appointments are cancelled.

    Past appointments are kept for history. Each affected patient gets an email.
    """
    doctor = db.scalar(select(Doctor).where(Doctor.id == doctor_id).with_for_update(of=Doctor))
    if doctor is None:
        raise NotFoundError("DOCTOR_NOT_FOUND", "Doctor not found.")
    doctor.is_active = False
    cancelled_ids = booking_service.cancel_bookings_by_clinic(
        db, booking_service.future_confirmed_bookings(db, [doctor.id])
    )
    db.commit()
    cache_service.invalidate_doctor(doctor.id)
    booking_service.notify_clinic_cancellations(db, cancelled_ids)
    return doctor


def count_available_slots_by_doctor(db: Session, local_date: date) -> dict[int, int]:
    """Return {doctor_id: number of free future slots} for one clinic-local day."""
    day_start, day_end = local_day_bounds_utc(local_date)
    earliest_start = max(day_start, now_utc())
    query = (
        select(Slot.doctor_id, func.count(Slot.id))
        .where(Slot.status == SlotStatus.AVAILABLE.value)
        .where(Slot.start_time >= earliest_start)
        .where(Slot.start_time < day_end)
        .group_by(Slot.doctor_id)
    )
    counts = {}
    for doctor_id, slot_count in db.execute(query):
        counts[doctor_id] = slot_count
    return counts


def search_doctors(
    db: Session,
    specialty: str | None,
    city: str | None,
    local_date: date | None,
) -> list[DoctorSearchResult]:
    """Find active doctors by specialty and city. With a date, only doctors with free slots that day."""
    query = (
        select(Doctor)
        .join(Doctor.clinic)
        .join(Doctor.user)
        .where(Doctor.is_active.is_(True))
        .where(Clinic.is_active.is_(True))
        .order_by(User.full_name)
    )
    if specialty:
        query = query.where(func.lower(Doctor.specialty) == specialty.strip().lower())
    if city:
        query = query.where(func.lower(Clinic.city) == city.strip().lower())

    doctors = list(db.scalars(query))

    slot_counts = None
    if local_date is not None:
        slot_counts = count_available_slots_by_doctor(db, local_date)

    results = []
    for doctor in doctors:
        result = DoctorSearchResult.from_doctor(doctor)
        if slot_counts is not None:
            available_count = slot_counts.get(doctor.id, 0)
            if available_count == 0:
                continue
            result.available_slot_count = available_count
        results.append(result)
    return results


def get_search_filters(db: Session) -> SearchFilters:
    """Distinct specialties and cities, used to fill the search dropdowns."""
    specialties_query = (
        select(Doctor.specialty).where(Doctor.is_active.is_(True)).distinct().order_by(Doctor.specialty)
    )
    cities_query = select(Clinic.city).where(Clinic.is_active.is_(True)).distinct().order_by(Clinic.city)
    return SearchFilters(
        specialties=list(db.scalars(specialties_query)),
        cities=list(db.scalars(cities_query)),
    )
