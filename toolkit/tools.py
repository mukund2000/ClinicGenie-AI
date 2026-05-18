from sqlite3 import IntegrityError
from typing import Optional

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
    list_doctors,
    list_specializations,
    reschedule_appointment as reschedule_patient_appointment,
)
from observability import observe_operation


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


def _normalize_catalog_value(value: str) -> str:
    return value.strip().casefold()


def _match_catalog_value(value: str, catalog: list[str]) -> Optional[str]:
    normalized_value = _normalize_catalog_value(value)
    for item in catalog:
        if _normalize_catalog_value(item) == normalized_value:
            return item
    return None


def _format_catalog_values(values: list[str]) -> str:
    if not values:
        return "none configured"
    return ", ".join(values)


@observe_operation(layer="tool", logger_name=__name__)
def get_catalog_prompt_context() -> str:
    return (
        "Available doctors from the appointment database:\n"
        f"{_format_catalog_values(list_doctors())}\n\n"
        "Available specializations from the appointment database:\n"
        f"{_format_catalog_values(list_specializations())}"
    )


def _unknown_doctor_message() -> str:
    return (
        "Doctor not found in the appointment database. Available doctors: "
        f"{_format_catalog_values(list_doctors())}."
    )


def _unknown_specialization_message() -> str:
    return (
        "Specialization not found in the appointment database. Available specializations: "
        f"{_format_catalog_values(list_specializations())}."
    )


@tool
@observe_operation(layer="tool", logger_name=__name__)
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
@observe_operation(layer="tool", logger_name=__name__)
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
@observe_operation(layer="tool", logger_name=__name__)
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
@observe_operation(layer="tool", logger_name=__name__)
def check_availability_by_doctor(
    desired_date: DateModel,
    doctor_name: str,
):
    """
    Checking the database if we have availability for the specific doctor.
    The parameters should be mentioned by the user in the query.
    """
    matched_doctor = _match_catalog_value(doctor_name, list_doctors())
    if matched_doctor is None:
        return _unknown_doctor_message()

    rows = [
        appointment["date_slot"].split(" ")[-1]
        for appointment in get_available_slots_by_doctor(desired_date.date, matched_doctor)
    ]

    if len(rows) == 0:
        return "No availability in the entire day"

    output = f"This availability for {desired_date.date}\n"
    output += "Available slots: " + ", ".join(rows)
    return output


@tool
@observe_operation(layer="tool", logger_name=__name__)
def check_availability_by_specialization(
    desired_date: DateModel,
    specialization: str,
):
    """
    Checking the database if we have availability for the specific specialization.
    The parameters should be mentioned by the user in the query.
    """
    matched_specialization = _match_catalog_value(specialization, list_specializations())
    if matched_specialization is None:
        return _unknown_specialization_message()

    appointments = get_available_slots_by_specialization(
        desired_date.date,
        matched_specialization,
    )
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
@observe_operation(layer="tool", logger_name=__name__)
def set_appointment(
    desired_date: DateTimeModel,
    id_number: IdentificationNumberModel,
    doctor_name: str,
):
    """
    Set appointment or slot with the doctor.
    The parameters MUST be mentioned by the user in the query.
    """
    matched_doctor = _match_catalog_value(doctor_name, list_doctors())
    if matched_doctor is None:
        return _unknown_doctor_message()

    appointment = create_appointment(
        patient_id=id_number.id,
        doctor_name=matched_doctor,
        date_slot=desired_date.date,
    )
    if appointment is None:
        return "No available appointments for that particular case"
    return "Successfully done"


@tool
@observe_operation(layer="tool", logger_name=__name__)
def cancel_appointment(
    date: DateTimeModel,
    id_number: IdentificationNumberModel,
    doctor_name: str,
):
    """
    Canceling an appointment.
    The parameters MUST be mentioned by the user in the query.
    """
    matched_doctor = _match_catalog_value(doctor_name, list_doctors())
    if matched_doctor is None:
        return _unknown_doctor_message()

    appointment = cancel_patient_appointment(
        patient_id=id_number.id,
        doctor_name=matched_doctor,
        date_slot=date.date,
    )
    if appointment is None:
        return "You do not have any appointment with those specifications"
    return "Successfully cancelled"


@tool
@observe_operation(layer="tool", logger_name=__name__)
def reschedule_appointment(
    old_date: DateTimeModel,
    new_date: DateTimeModel,
    id_number: IdentificationNumberModel,
    doctor_name: str,
):
    """
    Rescheduling an appointment.
    The parameters MUST be mentioned by the user in the query.
    """
    matched_doctor = _match_catalog_value(doctor_name, list_doctors())
    if matched_doctor is None:
        return _unknown_doctor_message()

    appointment = reschedule_patient_appointment(
        patient_id=id_number.id,
        doctor_name=matched_doctor,
        old_date_slot=old_date.date,
        new_date_slot=new_date.date,
    )
    if appointment is None:
        return "Not available slots in the desired period"
    return "Successfully rescheduled for the desired time"
