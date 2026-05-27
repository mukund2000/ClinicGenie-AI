import json
import os
import socket
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st


API_BASE_URL = os.getenv(
    "CLINICGENIE_API_BASE_URL",
    "https://clinicgenie-ai.onrender.com",
).rstrip("/")
API_TIMEOUT_SECONDS = int(os.getenv("CLINICGENIE_API_TIMEOUT_SECONDS", "20"))
CHAT_TIMEOUT_SECONDS = int(os.getenv("CLINICGENIE_CHAT_TIMEOUT_SECONDS", "120"))


st.set_page_config(page_title="ClinicGenie", page_icon="CG", layout="wide")

st.markdown(
    """
    <style>
    section.main > div {
        padding-bottom: 5.5rem;
    }

    div[data-testid="stChatInput"] {
        position: fixed;
        bottom: 1rem;
        z-index: 1000;
        background: var(--background-color);
        width: min(58rem, calc(100vw - 24rem));
    }

    @media (max-width: 900px) {
        div[data-testid="stChatInput"] {
            left: 1rem;
            right: 1rem;
            width: auto;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


class ApiClientError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def api_request(
    method: str,
    path: str,
    payload: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: int = API_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    query = ""
    if params:
        query = "?" + urlencode(
            {key: value for key, value in params.items() if value not in (None, "")}
        )

    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{API_BASE_URL}{path}{query}",
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.reason
        response_body = exc.read().decode("utf-8")
        if response_body:
            try:
                detail = json.loads(response_body).get("detail", detail)
            except json.JSONDecodeError:
                detail = response_body
        raise ApiClientError(str(detail), status_code=exc.code) from exc
    except URLError as exc:
        raise ApiClientError(
            f"Could not reach ClinicGenie API at {API_BASE_URL}. Start it with `uvicorn main:app --reload`."
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ApiClientError(
            f"ClinicGenie API did not respond within {timeout} seconds. "
            "The request may still be running; try again in a moment."
        ) from exc

    if not data:
        return {}
    return json.loads(data)


@st.cache_data(ttl=60)
def get_doctors() -> list[str]:
    return api_request("GET", "/doctors")["doctors"]


def set_selected_patient(patient: dict) -> None:
    st.session_state.selected_patient = patient


def render_patient_summary(patient: dict) -> None:
    st.write(f"Patient ID: `{patient['id']}`")
    st.write(f"Name: {patient['name']}")
    st.write(f"Email: {patient.get('email') or 'Not provided'}")
    st.write(f"Phone: {patient.get('phone') or 'Not provided'}")
    st.write(f"DOB: {patient.get('dob') or 'Not provided'}")


if "selected_patient" not in st.session_state:
    st.session_state.selected_patient = None

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hi, I can help you check availability, book, cancel, or "
                "reschedule appointments. For patient-specific requests, "
                "please provide an email or phone number so I can look up "
                "the patient first."
            ),
        }
    ]

if "available_slots" not in st.session_state:
    st.session_state.available_slots = []

if "availability_context" not in st.session_state:
    st.session_state.availability_context = None

st.title("ClinicGenie Appointment Console")
st.caption("Chat with the assistant, manage patients, and book appointments from one database-backed workspace.")

with st.sidebar:
    st.subheader("API")
    st.write(f"Base URL: `{API_BASE_URL}`")
    try:
        health = api_request("GET", "/health")
    except ApiClientError as exc:
        st.error(str(exc))
    else:
        st.success(f"Status: {health.get('status', 'unknown')}")

    st.divider()
    st.subheader("Current patient")
    if st.session_state.selected_patient:
        render_patient_summary(st.session_state.selected_patient)
        if st.button("Clear selected patient"):
            st.session_state.selected_patient = None
            st.rerun()
    else:
        st.write("No patient selected.")

    st.divider()
    st.subheader("Formats")
    st.write("Availability date: `DD-MM-YYYY`")
    st.write("Appointment slot: `DD-MM-YYYY HH:MM`")

tab_chat, tab_patients, tab_booking = st.tabs(
    ["Chatbot", "Patients", "Book Appointment"]
)

with tab_chat:
    st.subheader("Assistant")

    if st.button("Clear chat"):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Chat cleared. How can I help with your appointment?",
            }
        ]
        st.rerun()

    with st.container(height=520):
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

    user_input = st.chat_input("Ask ClinicGenie...")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Checking appointment details..."):
                try:
                    chat_response = api_request(
                        "POST",
                        "/chat",
                        payload={
                            "message": user_input,
                            "history": st.session_state.messages[:-1],
                        },
                        timeout=CHAT_TIMEOUT_SECONDS,
                    )
                    assistant_response = chat_response["response"]
                except ApiClientError as exc:
                    assistant_response = f"Sorry, I could not process that request: {exc}"

            st.write(assistant_response)

        st.session_state.messages.append(
            {"role": "assistant", "content": assistant_response}
        )

with tab_patients:
    lookup_col, register_col = st.columns(2)

    with lookup_col:
        st.subheader("Patient Lookup")
        with st.form("patient_lookup_form"):
            lookup_email = st.text_input("Email", key="lookup_email")
            lookup_phone = st.text_input("Phone", key="lookup_phone")
            lookup_submitted = st.form_submit_button("Look up patient")

        if lookup_submitted:
            if not lookup_email and not lookup_phone:
                st.warning("Enter an email or phone number.")
            else:
                try:
                    patient = api_request(
                        "GET",
                        "/patients/lookup",
                        params={
                            "email": lookup_email or None,
                            "phone": lookup_phone or None,
                        },
                    )
                except ApiClientError as exc:
                    st.error(str(exc))
                else:
                    set_selected_patient(patient)
                    st.success("Patient selected.")
                    render_patient_summary(patient)

    with register_col:
        st.subheader("Patient Registration")
        with st.form("patient_registration_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            dob = st.text_input("Date of birth")
            register_submitted = st.form_submit_button("Register patient")

        if register_submitted:
            if not name:
                st.warning("Patient name is required.")
            elif not email and not phone:
                st.warning("Provide at least an email or phone number.")
            else:
                try:
                    patient = api_request(
                        "POST",
                        "/patients",
                        payload={
                            "name": name,
                            "email": email or None,
                            "phone": phone or None,
                            "dob": dob or None,
                        },
                    )
                except ApiClientError as exc:
                    st.error(str(exc))
                else:
                    set_selected_patient(patient)
                    st.success("Patient registered and selected.")
                    render_patient_summary(patient)

    st.divider()
    st.subheader("Patient History")
    patient = st.session_state.selected_patient
    if patient is None:
        st.info("Look up or register a patient to view history.")
    else:
        render_patient_summary(patient)
        if st.button("Refresh history"):
            st.rerun()

        try:
            history_response = api_request("GET", f"/patients/{patient['id']}/history")
        except ApiClientError as exc:
            st.error(str(exc))
        else:
            history = history_response["history"]
            if len(history) == 0:
                st.write("No appointment history found.")
            else:
                st.dataframe(history, use_container_width=True, hide_index=True)

with tab_booking:
    st.subheader("Book Appointment With Patient Context")

    patient = st.session_state.selected_patient
    if patient is None:
        st.info("Select a patient from the Patients tab before booking.")
    else:
        patient_col, booking_col = st.columns([1, 2])

        with patient_col:
            st.write("Selected patient")
            render_patient_summary(patient)

        with booking_col:
            try:
                doctors = get_doctors()
            except ApiClientError as exc:
                st.error(str(exc))
                doctors = []

            if len(doctors) == 0:
                st.info("No doctors are configured in the appointment catalog.")
                st.session_state.available_slots = []
                st.session_state.availability_context = None
                check_availability = False
            else:
                with st.form("appointment_booking_form"):
                    doctor_name = st.selectbox("Doctor", doctors)
                    availability_date = st.text_input("Availability date", value="05-08-2024")
                    check_availability = st.form_submit_button("Check availability")

                if check_availability:
                    try:
                        availability = api_request(
                            "GET",
                            "/appointments/availability/doctor",
                            params={
                                "date": availability_date,
                                "doctor_name": doctor_name,
                            },
                        )
                    except ApiClientError as exc:
                        st.error(str(exc))
                    else:
                        slots = availability["available_slots"]
                        if len(slots) == 0:
                            st.warning("No available slots for that doctor and date.")
                            st.session_state.available_slots = []
                            st.session_state.availability_context = None
                        else:
                            st.session_state.available_slots = slots
                            st.session_state.availability_context = {
                                "doctor_name": doctor_name,
                                "date": availability_date,
                            }
                            st.success(f"Found {len(slots)} available slots.")

            slots = st.session_state.available_slots
            slot_options = [slot["date_slot"] for slot in slots]

            if len(slot_options) == 0:
                st.info("Check availability to choose a slot.")
                book_submitted = False
                date_slot = None
            else:
                context = st.session_state.availability_context or {}
                st.write(
                    "Booking from availability search: "
                    f"{context.get('doctor_name')} on {context.get('date')}"
                )
                with st.form("confirm_booking_form"):
                    date_slot = st.selectbox("Appointment slot", slot_options)
                    book_submitted = st.form_submit_button("Book appointment")

            if book_submitted:
                context = st.session_state.availability_context or {}
                try:
                    appointment = api_request(
                        "POST",
                        "/appointments/book",
                        payload={
                            "patient_id": patient["id"],
                            "doctor_name": context["doctor_name"],
                            "date_slot": date_slot,
                        },
                    )
                except ApiClientError as exc:
                    st.error(str(exc))
                else:
                    st.success("Appointment booked.")
                    st.json(appointment)
                    st.session_state.available_slots = [
                        slot for slot in slots if slot["date_slot"] != date_slot
                    ]
