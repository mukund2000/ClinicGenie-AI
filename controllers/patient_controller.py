from sqlite3 import IntegrityError
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.database import (
    create_patient,
    get_patient,
    get_patient_by_contact,
    get_patient_by_email,
    get_patient_by_phone,
    get_patient_history,
    update_patient,
)


router = APIRouter(tags=["patients"])


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


@router.post("/patients", status_code=status.HTTP_201_CREATED)
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


@router.get("/patients/lookup")
def lookup_patient(
    email: Optional[str] = Query(default=None),
    phone: Optional[str] = Query(default=None),
) -> dict:
    patient = get_patient_by_contact(email=email, phone=phone)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@router.get("/patients/by-email/{email}")
def lookup_patient_by_email(email: str) -> dict:
    patient = get_patient_by_email(email)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@router.get("/patients/by-phone/{phone}")
def lookup_patient_by_phone(phone: str) -> dict:
    patient = get_patient_by_phone(phone)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@router.get("/patients/{patient_id}")
def read_patient(patient_id: int) -> dict:
    patient = get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@router.patch("/patients/{patient_id}")
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


@router.get("/patients/{patient_id}/history")
def patient_history(patient_id: int) -> dict:
    if get_patient(patient_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return {"patient_id": patient_id, "history": get_patient_history(patient_id)}
