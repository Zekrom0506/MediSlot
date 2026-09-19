from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Clinic
from app.schemas.clinic import ClinicCreate, ClinicUpdate


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
    """Change only the fields that were sent."""
    clinic = get_clinic(db, clinic_id)
    changes = request.model_dump(exclude_unset=True)
    if "city" in changes and changes["city"] is not None:
        changes["city"] = changes["city"].strip().title()
    for field_name, value in changes.items():
        setattr(clinic, field_name, value)
    db.commit()
    return clinic


def deactivate_clinic(db: Session, clinic_id: int) -> Clinic:
    """Hide a clinic (and its doctors) from search without deleting history."""
    clinic = get_clinic(db, clinic_id)
    clinic.is_active = False
    db.commit()
    return clinic
