from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from agent.appointment_agent import ClinicGenieAppointmentAgent, message_from_role
from core.database import (
    cancel_appointment as cancel_patient_appointment,
    create_appointment,
    get_available_slots_by_doctor,
    get_available_slots_by_specialization,
    get_patient,
    get_patient_history,
    list_doctors,
    list_specializations,
    reschedule_appointment as reschedule_patient_appointment,
)
from shared.observability import get_logger


router = APIRouter(tags=["appointments", "chat"])
logger = get_logger(__name__)
agent: Optional[ClinicGenieAppointmentAgent] = None


class AppointmentRequest(BaseModel):
    patient_id: int
    doctor_name: str
    date_slot: str = Field(pattern=r"^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$")


class RescheduleRequest(BaseModel):
    patient_id: int
    doctor_name: str
    old_date_slot: str = Field(pattern=r"^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$")
    new_date_slot: str = Field(pattern=r"^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


@router.get("/doctors")
def doctors() -> dict[str, list[str]]:
    return {"doctors": list_doctors()}


@router.get("/specializations")
def specializations() -> dict[str, list[str]]:
    return {"specializations": list_specializations()}


@router.get("/catalog")
def catalog() -> dict[str, list[str]]:
    return {
        "doctors": list_doctors(),
        "specializations": list_specializations(),
    }


@router.get("/appointments/history/{patient_id}")
def appointment_history(patient_id: int) -> dict:
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return {"patient_id": patient_id, "history": get_patient_history(patient_id)}


@router.get("/appointments/availability/doctor")
def availability_by_doctor(
    date: str = Query(pattern=r"^\d{2}-\d{2}-\d{4}$"),
    doctor_name: str = Query(min_length=1),
) -> dict:
    return {
        "date": date,
        "doctor_name": doctor_name,
        "available_slots": get_available_slots_by_doctor(date, doctor_name),
    }


@router.get("/appointments/availability/specialization")
def availability_by_specialization(
    date: str = Query(pattern=r"^\d{2}-\d{2}-\d{4}$"),
    specialization: str = Query(min_length=1),
) -> dict:
    return {
        "date": date,
        "specialization": specialization,
        "available_slots": get_available_slots_by_specialization(date, specialization),
    }


@router.post("/appointments/book", status_code=status.HTTP_201_CREATED)
def book_appointment(payload: AppointmentRequest) -> dict:
    appointment = create_appointment(
        patient_id=payload.patient_id,
        doctor_name=payload.doctor_name,
        date_slot=payload.date_slot,
    )
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patient not found or requested slot is unavailable.",
        )
    return appointment


@router.post("/appointments/cancel")
def cancel_appointment(payload: AppointmentRequest) -> dict:
    appointment = cancel_patient_appointment(
        patient_id=payload.patient_id,
        doctor_name=payload.doctor_name,
        date_slot=payload.date_slot,
    )
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching appointment was not found.",
        )
    return appointment


@router.post("/appointments/reschedule")
def reschedule_appointment(payload: RescheduleRequest) -> dict:
    appointment = reschedule_patient_appointment(
        patient_id=payload.patient_id,
        doctor_name=payload.doctor_name,
        old_date_slot=payload.old_date_slot,
        new_date_slot=payload.new_date_slot,
    )
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Existing appointment not found or requested new slot is unavailable.",
        )
    return appointment


@router.post("/chat")
def chat(payload: ChatRequest) -> dict[str, str]:
    global agent
    if agent is None:
        logger.info("agent_lazy_initialization_started", extra={"layer": "api"})
        agent = ClinicGenieAppointmentAgent()
        logger.info("agent_lazy_initialization_succeeded", extra={"layer": "api"})

    messages = [message_from_role(item.role, item.content) for item in payload.history]
    messages.append(message_from_role("user", payload.message))
    result_messages = agent.invoke_messages(messages)
    return {"response": str(result_messages[-1].content)}
