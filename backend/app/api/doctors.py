from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.doctor import DoctorResponse, DoctorSearchResult, SearchFilters
from app.schemas.slot import NotPastDate, SlotResponse
from app.services import doctor_service, slot_service

router = APIRouter(prefix="/api/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorSearchResult])
def search_doctors(
    db: DbSession,
    specialty: str | None = None,
    city: str | None = None,
    date: NotPastDate | None = None,
) -> list[DoctorSearchResult]:
    """Search doctors. Passing a date only returns doctors with free slots that day."""
    return doctor_service.search_doctors(db, specialty, city, date)


@router.get("/filters", response_model=SearchFilters)
def search_filters(db: DbSession) -> SearchFilters:
    """Available specialties and cities for the search form."""
    return doctor_service.get_search_filters(db)


@router.get("/{doctor_id}", response_model=DoctorResponse)
def get_doctor(doctor_id: int, db: DbSession) -> DoctorResponse:
    """Public doctor profile."""
    doctor = doctor_service.get_active_doctor(db, doctor_id)
    return DoctorResponse.from_doctor(doctor)


@router.get("/{doctor_id}/slots", response_model=list[SlotResponse])
def get_available_slots(doctor_id: int, date: NotPastDate, db: DbSession) -> list[SlotResponse]:
    """Free slots for a doctor on a date (clinic time)."""
    doctor_service.get_active_doctor(db, doctor_id)
    slots = slot_service.list_available_slots(db, doctor_id, date)
    return [SlotResponse.model_validate(slot) for slot in slots]
