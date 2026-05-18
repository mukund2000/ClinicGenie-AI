import time
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlite3 import IntegrityError

from appointment_agent import ClinicGenieAppointmentAgent, message_from_role
from database import (
    check_database_health,
    count_appointments,
    create_appointment,
    create_patient,
    get_available_slots_by_doctor,
    get_available_slots_by_specialization,
    get_patient,
    get_patient_by_contact,
    get_patient_by_email,
    get_patient_by_phone,
    get_patient_history,
    initialize_database,
    list_doctors,
    list_specializations,
    seed_appointments_from_csv,
    update_patient,
    cancel_appointment as cancel_patient_appointment,
    reschedule_appointment as reschedule_patient_appointment,
)
from observability import get_logger, metrics


app = FastAPI(
    title="ClinicGenie API",
    description="Patient onboarding, lookup, appointment scheduling, and chatbot API.",
    version="1.0.0",
)

agent: Optional[ClinicGenieAppointmentAgent] = None
logger = get_logger(__name__)


def _safe_request_path(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        return str(route_path)

    path = request.url.path
    if path.startswith("/patients/by-email/"):
        return "/patients/by-email/{email}"
    if path.startswith("/patients/by-phone/"):
        return "/patients/by-phone/{phone}"
    return path


class PatientCreate(BaseModel):
    name: str = Field(min_length=1)
    email: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[str] = None


class PatientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    email: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[str] = None


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


@app.middleware("http")
async def log_api_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    started_at = time.perf_counter()
    path = _safe_request_path(request)
    method = request.method

    metrics.increment("api.requests.started")
    metrics.increment(f"api.requests.{method}.{path}.started")
    logger.info(
        "api_request_started",
        extra={
            "layer": "api",
            "request_id": request_id,
            "method": method,
            "path": path,
            "client": request.client.host if request.client else None,
        },
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started_at) * 1000
        metrics.increment("api.requests.failed")
        path = _safe_request_path(request)
        metrics.increment(f"api.requests.{method}.{path}.failed")
        metrics.observe_duration("api.requests.duration_ms", duration_ms)
        logger.exception(
            "api_request_failed",
            extra={
                "layer": "api",
                "request_id": request_id,
                "method": method,
                "path": path,
                "duration_ms": round(duration_ms, 3),
            },
        )
        raise

    duration_ms = (time.perf_counter() - started_at) * 1000
    path = _safe_request_path(request)
    metrics.increment("api.requests.succeeded")
    metrics.increment(f"api.requests.{method}.{path}.succeeded")
    metrics.increment(f"api.responses.{response.status_code}")
    metrics.observe_duration("api.requests.duration_ms", duration_ms)
    response.headers["x-request-id"] = request_id
    logger.info(
        "api_request_succeeded",
        extra={
            "layer": "api",
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 3),
        },
    )
    return response


@app.on_event("startup")
def startup() -> None:
    logger.info("api_startup_started", extra={"layer": "api"})
    initialize_database()
    if count_appointments() == 0:
        inserted_count = seed_appointments_from_csv()
        logger.info(
            "appointments_seeded",
            extra={"layer": "api", "inserted_count": inserted_count},
        )
    logger.info("api_startup_succeeded", extra={"layer": "api"})


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "checks": {
            "api": {"status": "ok"},
            "database": check_database_health(),
        },
    }


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict:
    database_health = check_database_health()
    return {
        "status": database_health["status"],
        "checks": {"database": database_health},
    }


@app.get("/metrics")
def read_metrics() -> dict:
    return metrics.snapshot()


@app.get("/doctors")
def doctors() -> dict[str, list[str]]:
    return {"doctors": list_doctors()}


@app.get("/specializations")
def specializations() -> dict[str, list[str]]:
    return {"specializations": list_specializations()}


@app.get("/catalog")
def catalog() -> dict[str, list[str]]:
    return {
        "doctors": list_doctors(),
        "specializations": list_specializations(),
    }


@app.post("/patients", status_code=status.HTTP_201_CREATED)
def onboard_patient(payload: PatientCreate) -> dict:
    if not payload.email and not payload.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one contact method: email or phone.",
        )

    try:
        return create_patient(
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            dob=payload.dob,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with that email or phone already exists.",
        ) from exc


@app.get("/patients/lookup")
def lookup_patient(
    email: Optional[str] = Query(default=None),
    phone: Optional[str] = Query(default=None),
) -> dict:
    patient = get_patient_by_contact(email=email, phone=phone)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@app.get("/patients/by-email/{email}")
def lookup_patient_by_email(email: str) -> dict:
    patient = get_patient_by_email(email)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@app.get("/patients/by-phone/{phone}")
def lookup_patient_by_phone(phone: str) -> dict:
    patient = get_patient_by_phone(phone)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@app.get("/patients/{patient_id}")
def read_patient(patient_id: int) -> dict:
    patient = get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@app.patch("/patients/{patient_id}")
def patch_patient(patient_id: int, payload: PatientUpdate) -> dict:
    try:
        patient = update_patient(
            patient_id=patient_id,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            dob=payload.dob,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with that email or phone already exists.",
        ) from exc

    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@app.get("/patients/{patient_id}/history")
def patient_history(patient_id: int) -> dict:
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return {"patient_id": patient_id, "history": get_patient_history(patient_id)}


@app.get("/appointments/history/{patient_id}")
def appointment_history(patient_id: int) -> dict:
    return patient_history(patient_id)


@app.get("/appointments/availability/doctor")
def availability_by_doctor(
    date: str = Query(pattern=r"^\d{2}-\d{2}-\d{4}$"),
    doctor_name: str = Query(min_length=1),
) -> dict:
    return {
        "date": date,
        "doctor_name": doctor_name,
        "available_slots": get_available_slots_by_doctor(date, doctor_name),
    }


@app.get("/appointments/availability/specialization")
def availability_by_specialization(
    date: str = Query(pattern=r"^\d{2}-\d{2}-\d{4}$"),
    specialization: str = Query(min_length=1),
) -> dict:
    return {
        "date": date,
        "specialization": specialization,
        "available_slots": get_available_slots_by_specialization(date, specialization),
    }


@app.post("/appointments/book", status_code=status.HTTP_201_CREATED)
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


@app.post("/appointments/cancel")
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


@app.post("/appointments/reschedule")
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


@app.post("/chat")
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
