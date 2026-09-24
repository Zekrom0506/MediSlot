from datetime import date
from typing import Literal

from fastapi import APIRouter

from app.api.deps import DbSession, DoctorUser
from app.schemas.booking import AppointmentOutcomeUpdate, DoctorAppointmentResponse
from app.schemas.doctor import DoctorResponse
from app.schemas.schedule import ScheduleEntryResponse, WeeklyScheduleUpdate
from app.schemas.slot import BlockDayRequest, BlockDayResponse, SlotResponse
from app.services import booking_service, doctor_service, schedule_service, slot_service

router = APIRouter(prefix="/api/doctor", tags=["doctor portal"])


@router.get("/me", response_model=DoctorResponse)
def my_profile(current_user: DoctorUser, db: DbSession) -> DoctorResponse:
    """The logged-in doctor's own profile."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    return DoctorResponse.from_doctor(doctor)


@router.get("/schedule", response_model=list[ScheduleEntryResponse])
def get_schedule(current_user: DoctorUser, db: DbSession) -> list[ScheduleEntryResponse]:
    """The doctor's weekly schedule."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    entries = schedule_service.get_schedule(db, doctor)
    return [ScheduleEntryResponse.model_validate(entry) for entry in entries]


@router.put("/schedule", response_model=list[ScheduleEntryResponse])
def replace_schedule(
    request: WeeklyScheduleUpdate, current_user: DoctorUser, db: DbSession
) -> list[ScheduleEntryResponse]:
    """Replace the whole weekly schedule and regenerate upcoming slots."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    entries = schedule_service.replace_schedule(db, doctor, request.entries)
    return [ScheduleEntryResponse.model_validate(entry) for entry in entries]


@router.get("/slots", response_model=list[SlotResponse])
def get_my_slots(date: date, current_user: DoctorUser, db: DbSession) -> list[SlotResponse]:
    """All of the doctor's slots on a day, including booked and blocked ones."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    slots = slot_service.list_all_slots_for_day(db, doctor.id, date)
    return [SlotResponse.model_validate(slot) for slot in slots]


@router.post("/slots/{slot_id}/block", response_model=SlotResponse)
def block_slot(slot_id: int, current_user: DoctorUser, db: DbSession) -> SlotResponse:
    """Block one free slot."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    slot = slot_service.block_slot(db, doctor, slot_id)
    return SlotResponse.model_validate(slot)


@router.post("/slots/{slot_id}/unblock", response_model=SlotResponse)
def unblock_slot(slot_id: int, current_user: DoctorUser, db: DbSession) -> SlotResponse:
    """Make a blocked slot bookable again."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    slot = slot_service.unblock_slot(db, doctor, slot_id)
    return SlotResponse.model_validate(slot)


@router.post("/block-day", response_model=BlockDayResponse)
def block_day(request: BlockDayRequest, current_user: DoctorUser, db: DbSession) -> BlockDayResponse:
    """Block all free slots on a whole day, e.g. for a holiday."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    blocked_count, booked_count = slot_service.block_day(db, doctor, request.date)
    return BlockDayResponse(blocked_count=blocked_count, booked_count=booked_count)


@router.get("/appointments", response_model=list[DoctorAppointmentResponse])
def my_appointments(
    current_user: DoctorUser, db: DbSession, scope: Literal["today", "upcoming"] = "today"
) -> list[DoctorAppointmentResponse]:
    """Today's appointments or all upcoming ones."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    bookings = booking_service.list_doctor_appointments(db, doctor, scope)
    return [DoctorAppointmentResponse.from_booking(booking) for booking in bookings]


@router.patch("/appointments/{booking_id}", response_model=DoctorAppointmentResponse)
def record_outcome(
    booking_id: int, request: AppointmentOutcomeUpdate, current_user: DoctorUser, db: DbSession
) -> DoctorAppointmentResponse:
    """Mark an appointment as completed or no-show."""
    doctor = doctor_service.get_doctor_for_user(db, current_user)
    booking = booking_service.record_appointment_outcome(db, doctor, booking_id, request.status)
    return DoctorAppointmentResponse.from_booking(booking)
