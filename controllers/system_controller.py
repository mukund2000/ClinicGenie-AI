from fastapi import APIRouter

from core.database import check_database_health
from shared.observability import metrics


router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "checks": {
            "api": {"status": "ok"},
            "database": check_database_health(),
        },
    }


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness() -> dict:
    database_health = check_database_health()
    return {
        "status": database_health["status"],
        "checks": {"database": database_health},
    }


@router.get("/metrics")
def read_metrics() -> dict:
    return metrics.snapshot()
