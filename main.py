import time
from uuid import uuid4

from fastapi import FastAPI, Request

from controllers.appointment_chat_controller import router as appointment_chat_router
from controllers.doctor_availability_controller import router as doctor_availability_router
from controllers.patient_controller import router as patient_router
from controllers.system_controller import router as system_router
from core.database import (
    count_appointments,
    initialize_database,
    seed_appointments_from_csv,
)
from shared.observability import get_logger, metrics


app = FastAPI(
    title="ClinicGenie API",
    description="Patient onboarding, lookup, appointment scheduling, and chatbot API.",
    version="1.0.0",
)

logger = get_logger(__name__)

app.include_router(patient_router)
app.include_router(appointment_chat_router)
app.include_router(doctor_availability_router)
app.include_router(system_router)


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
