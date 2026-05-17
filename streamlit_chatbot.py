from sqlite3 import IntegrityError

import streamlit as st

from appointment_agent import ClinicGenieAppointmentAgent, message_from_role
from database import (
    count_appointments,
    create_appointment,
    create_patient,
    get_available_slots_by_doctor,
    get_patient_by_contact,
    get_patient_history,
    initialize_database,
    seed_appointments_from_csv,
)


DOCTORS = [
    "john doe",
    "jane smith",
    "emily johnson",
    "lisa brown",
    "michael green",
    "sarah wilson",
    "daniel miller",
    "susan davis",
    "robert martinez",
    "kevin anderson",
]


st.set_page_config(page_title="ClinicGenie", page_icon="CG", layout="wide")


@st.cache_resource
def get_agent() -> ClinicGenieAppointmentAgent:
    return ClinicGenieAppointmentAgent()


@st.cache_resource
def prepare_database() -> bool:
    initialize_database()
    if count_appointments() == 0:
        seed_appointments_from_csv()
    return True


def build_agent_messages():
    return [
        message_from_role(message["role"], message["content"])
        for message in st.session_state.messages
    ]


def set_selected_patient(patient: dict) -> None:
    st.session_state.selected_patient = patient


def render_patient_summary(patient: dict) -> None:
    st.write(f"Patient ID: `{patient['id']}`")
    st.write(f"Name: {patient['name']}")
    st.write(f"Email: {patient.get('email') or 'Not provided'}")
    st.write(f"Phone: {patient.get('phone') or 'Not provided'}")
    st.write(f"DOB: {patient.get('dob') or 'Not provided'}")


prepare_database()

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
st.caption("Chat with the assistant, manage patients, and book appointments from one SQLite-backed workspace.")

with st.sidebar:
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
                    agent = get_agent()
                    result_messages = agent.invoke_messages(build_agent_messages())
                    assistant_response = result_messages[-1].content
                except Exception as exc:
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
                patient = get_patient_by_contact(
                    email=lookup_email or None,
                    phone=lookup_phone or None,
                )
                if patient is None:
                    st.error("No patient found for that contact.")
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
                    patient = create_patient(
                        name=name,
                        email=email or None,
                        phone=phone or None,
                        dob=dob or None,
                    )
                except IntegrityError:
                    st.error("A patient with that email or phone already exists.")
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

        history = get_patient_history(patient["id"])
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
            with st.form("appointment_booking_form"):
                doctor_name = st.selectbox("Doctor", DOCTORS)
                availability_date = st.text_input("Availability date", value="05-08-2024")
                check_availability = st.form_submit_button("Check availability")

            if check_availability:
                slots = get_available_slots_by_doctor(availability_date, doctor_name)
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
                appointment = create_appointment(
                    patient_id=patient["id"],
                    doctor_name=context["doctor_name"],
                    date_slot=date_slot,
                )
                if appointment is None:
                    st.error("Slot is no longer available or patient could not be found.")
                else:
                    st.success("Appointment booked.")
                    st.json(appointment)
                    st.session_state.available_slots = [
                        slot for slot in slots if slot["date_slot"] != date_slot
                    ]
