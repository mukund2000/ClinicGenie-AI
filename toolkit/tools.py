from sqlite3 import IntegrityError
from typing import Literal, Optional

from langchain_core.tools import tool

from data_models.models import DateModel, DateTimeModel, IdentificationNumberModel
from database import (
    cancel_appointment as cancel_patient_appointment,
    create_appointment,
    create_patient,
    get_available_slots_by_doctor,
    get_available_slots_by_specialization,
    get_patient_by_contact,
    get_patient_history,
    reschedule_appointment as reschedule_patient_appointment,
)


DoctorName = Literal[
    "kevin anderson",
    "robert martinez",
    "susan davis",
    "daniel miller",
    "sarah wilson",
    "michael green",
    "lisa brown",
    "jane smith",
    "emily johnson",
    "john doe",
]

Specialization = Literal[
    "general_dentist",
    "cosmetic_dentist",
    "prosthodontist",
    "pediatric_dentist",
    "emergency_dentist",
    "oral_surgeon",
    "orthodontist",
]


def _to_am_pm(time_str: str) -> str:
    hours, minutes = map(int, str(time_str).split(":"))
    period = "AM" if hours < 12 else "PM"
    hours = hours % 12 or 12
    return f"{hours}:{minutes:02d} {period}"


def _format_patient(patient: dict) -> str:
    email = patient.get("email") or "not provided"
    phone = patient.get("phone") or "not provided"
    dob = patient.get("dob") or "not provided"
    return (
        f"Patient found. ID: {patient['id']}. "
        f"Name: {patient['name']}. Email: {email}. Phone: {phone}. DOB: {dob}."
    )


@tool
def lookup_patient(
    email: Optional[str] = None,
    phone: Optional[str] = None,
):
    """
    Look up a patient by email or phone before booking, cancelling, rescheduling,
    or retrieving appointment history.
    """
    if not email and not phone:
        return "Please provide at least an email or phone number to look up the patient."

    patient = get_patient_by_contact(email=email, phone=phone)
    if patient is None:
        return "No patient found for that contact. Please onboard the patient before booking."
    return _format_patient(patient)


@tool
def onboard_patient(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    dob: Optional[str] = None,
):
    """
    Create a new patient profile. Use this only after patient lookup returns no
    patient and the user provides name plus at least one contact method.
    """
    if not name:
        return "Patient name is required for onboarding."
    if not email and not phone:
        return "Please provide at least an email or phone number to onboard the patient."

    try:
        patient = create_patient(name=name, email=email, phone=phone, dob=dob)
    except IntegrityError:
        return "A patient with that email or phone already exists. Please look up the patient first."

    return "Patient onboarded successfully. " + _format_patient(patient)


@tool
def retrieve_patient_history(
    id_number: IdentificationNumberModel,
):
    """
    Retrieve appointment history for an existing patient ID after contact lookup
    identifies the patient.
    """
    history = get_patient_history(id_number.id)
    if len(history) == 0:
        return "No appointment history found for this patient."

    output = "Patient appointment history:\n"
    for item in history:
        output += (
            f"- {item['created_at']}: {item['action']}."
            f" {item.get('details') or ''}\n"
        )
    return output


@tool
def check_availability_by_doctor(
    desired_date: DateModel,
    doctor_name: DoctorName,
):
    """
    Checking the database if we have availability for the specific doctor.
    The parameters should be mentioned by the user in the query.
    """
    rows = [
        appointment["date_slot"].split(" ")[-1]
        for appointment in get_available_slots_by_doctor(desired_date.date, doctor_name)
    ]

    if len(rows) == 0:
        return "No availability in the entire day"

    output = f"This availability for {desired_date.date}\n"
    output += "Available slots: " + ", ".join(rows)
    return output


@tool
def check_availability_by_specialization(
    desired_date: DateModel,
    specialization: Specialization,
):
    """
    Checking the database if we have availability for the specific specialization.
    The parameters should be mentioned by the user in the query.
    """
    appointments = get_available_slots_by_specialization(desired_date.date, specialization)
    slots_by_doctor: dict[str, list[str]] = {}
    for appointment in appointments:
        slots_by_doctor.setdefault(appointment["doctor_name"], []).append(
            appointment["date_slot"].split(" ")[-1]
        )

    if len(slots_by_doctor) == 0:
        return "No availability in the entire day"

    output = f"This availability for {desired_date.date}\n"
    for doctor, slots in slots_by_doctor.items():
        output += (
            doctor
            + ". Available slots: \n"
            + ", \n".join([_to_am_pm(slot) for slot in slots])
            + "\n"
        )
    return output


@tool
def set_appointment(
    desired_date: DateTimeModel,
    id_number: IdentificationNumberModel,
    doctor_name: DoctorName,
):
    """
    Set appointment or slot with the doctor.
    The parameters MUST be mentioned by the user in the query.
    """
    appointment = create_appointment(
        patient_id=id_number.id,
        doctor_name=doctor_name,
        date_slot=desired_date.date,
    )
    if appointment is None:
        return "No available appointments for that particular case"
    return "Successfully done"


@tool
def cancel_appointment(
    date: DateTimeModel,
    id_number: IdentificationNumberModel,
    doctor_name: DoctorName,
):
    """
    Canceling an appointment.
    The parameters MUST be mentioned by the user in the query.
    """
    appointment = cancel_patient_appointment(
        patient_id=id_number.id,
        doctor_name=doctor_name,
        date_slot=date.date,
    )
    if appointment is None:
        return "You do not have any appointment with those specifications"
    return "Successfully cancelled"


@tool
def reschedule_appointment(
    old_date: DateTimeModel,
    new_date: DateTimeModel,
    id_number: IdentificationNumberModel,
    doctor_name: DoctorName,
):
    """
    Rescheduling an appointment.
    The parameters MUST be mentioned by the user in the query.
    """
    appointment = reschedule_patient_appointment(
        patient_id=id_number.id,
        doctor_name=doctor_name,
        old_date_slot=old_date.date,
        new_date_slot=new_date.date,
    )
    if appointment is None:
        return "Not available slots in the desired period"
    return "Successfully rescheduled for the desired time"
