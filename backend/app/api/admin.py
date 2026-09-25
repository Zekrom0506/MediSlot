from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, DbSession
from app.schemas.admin import AdminStats
from app.schemas.clinic import ClinicCreate, ClinicResponse, ClinicUpdate
from app.schemas.doctor import DoctorCreate, DoctorResponse, DoctorUpdate
from app.schemas.slot import SlotGenerationResponse
from app.services import clinic_service, doctor_service, slot_service, stats_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/clinics", response_model=list[ClinicResponse])
def list_clinics(current_user: AdminUser, db: DbSession) -> list[ClinicResponse]:
    """Every clinic, including inactive ones."""
    clinics = clinic_service.list_clinics(db)
    return [ClinicResponse.model_validate(clinic) for clinic in clinics]


@router.post("/clinics", response_model=ClinicResponse, status_code=status.HTTP_201_CREATED)
def create_clinic(request: ClinicCreate, current_user: AdminUser, db: DbSession) -> ClinicResponse:
    """Add a clinic."""
    clinic = clinic_service.create_clinic(db, request)
    return ClinicResponse.model_validate(clinic)


@router.patch("/clinics/{clinic_id}", response_model=ClinicResponse)
def update_clinic(
    clinic_id: int, request: ClinicUpdate, current_user: AdminUser, db: DbSession
) -> ClinicResponse:
    """Edit a clinic."""
    clinic = clinic_service.update_clinic(db, clinic_id, request)
    return ClinicResponse.model_validate(clinic)


@router.post("/clinics/{clinic_id}/deactivate", response_model=ClinicResponse)
def deactivate_clinic(clinic_id: int, current_user: AdminUser, db: DbSession) -> ClinicResponse:
    """Deactivate a clinic."""
    clinic = clinic_service.deactivate_clinic(db, clinic_id)
    return ClinicResponse.model_validate(clinic)


@router.get("/doctors", response_model=list[DoctorResponse])
def list_doctors(current_user: AdminUser, db: DbSession) -> list[DoctorResponse]:
    """Every doctor, including inactive ones."""
    doctors = doctor_service.list_doctors(db)
    return [DoctorResponse.from_doctor(doctor) for doctor in doctors]


@router.post("/doctors", response_model=DoctorResponse, status_code=status.HTTP_201_CREATED)
def create_doctor(request: DoctorCreate, current_user: AdminUser, db: DbSession) -> DoctorResponse:
    """Create a doctor account and profile."""
    doctor = doctor_service.create_doctor(db, request)
    return DoctorResponse.from_doctor(doctor)


@router.patch("/doctors/{doctor_id}", response_model=DoctorResponse)
def update_doctor(
    doctor_id: int, request: DoctorUpdate, current_user: AdminUser, db: DbSession
) -> DoctorResponse:
    """Edit a doctor."""
    doctor = doctor_service.update_doctor(db, doctor_id, request)
    return DoctorResponse.from_doctor(doctor)


@router.post("/doctors/{doctor_id}/deactivate", response_model=DoctorResponse)
def deactivate_doctor(doctor_id: int, current_user: AdminUser, db: DbSession) -> DoctorResponse:
    """Deactivate a doctor."""
    doctor = doctor_service.deactivate_doctor(db, doctor_id)
    return DoctorResponse.from_doctor(doctor)


@router.post("/slots/generate", response_model=SlotGenerationResponse)
def generate_slots(current_user: AdminUser, db: DbSession) -> SlotGenerationResponse:
    """Run slot generation now instead of waiting for the nightly job."""
    created_count = slot_service.generate_slots_for_all_doctors(db)
    return SlotGenerationResponse(created_count=created_count)


@router.get("/stats", response_model=AdminStats)
def get_stats(
    current_user: AdminUser, db: DbSession, days: int = Query(default=14, ge=1, le=90)
) -> AdminStats:
    """Bookings per day, cancellation and no-show rates, and the busiest doctors."""
    return stats_service.get_admin_stats(db, days)
