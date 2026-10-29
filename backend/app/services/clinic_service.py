from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Clinic, Doctor
from app.schemas.clinic import ClinicCreate, ClinicUpdate
from app.services import booking_service, cache_service


def list_clinics(db: Session) -> list[Clinic]:
    """All clinics, active and inactive, for the admin screen."""
    return list(db.scalars(select(Clinic).order_by(Clinic.name)))


def get_clinic(db: Session, clinic_id: int) -> Clinic:
    """Fetch one clinic or raise a 404."""
    clinic = db.get(Clinic, clinic_id)
    if clinic is None:
        raise NotFoundError("CLINIC_NOT_FOUND", "Clinic not found.")
    return clinic


def create_clinic(db: Session, request: ClinicCreate) -> Clinic:
    """Add a new clinic."""
    clinic = Clinic(name=request.name, address=request.address, city=request.city.strip().title())
    db.add(clinic)
    db.commit()
    return clinic


def update_clinic(db: Session, clinic_id: int, request: ClinicUpdate) -> Clinic:
    """Change only the fields that were sent. Deactivating goes through deactivate_clinic()."""
    changes = request.model_dump(exclude_unset=True)
    is_active = changes.pop("is_active", None)
    if is_active is False:
        deactivate_clinic(db, clinic_id)
    elif is_active is True:
        changes["is_active"] = True
    clinic = get_clinic(db, clinic_id)
    if "city" in changes and changes["city"] is not None:
        changes["city"] = changes["city"].strip().title()
    for field_name, value in changes.items():
        setattr(clinic, field_name, value)
    db.commit()
    return clinic


def deactivate_clinic(db: Session, clinic_id: int) -> Clinic:
    """Hide a clinic and its doctors from search, and cancel their upcoming appointments.

    History is kept. Each doctor row is locked FOR UPDATE (in id order) first,
    so no booking for these doctors can be in progress while we cancel.
    """
    clinic = get_clinic(db, clinic_id)
    doctor_ids = list(
        db.scalars(
            select(Doctor.id).where(Doctor.clinic_id == clinic_id).order_by(Doctor.id).with_for_update()
        )
    )
    clinic.is_active = False
    cancelled_ids = booking_service.cancel_bookings_by_clinic(
        db, booking_service.future_confirmed_bookings(db, doctor_ids)
    )
    db.commit()
    for doctor_id in doctor_ids:
        cache_service.invalidate_doctor(doctor_id)
    booking_service.notify_clinic_cancellations(db, cancelled_ids)
    return clinic
