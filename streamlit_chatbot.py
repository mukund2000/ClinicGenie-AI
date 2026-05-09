import streamlit as st

from appointment_agent import ClinicGenieAppointmentAgent, message_from_role


st.set_page_config(page_title="ClinicGenie Chatbot", page_icon="CG")


@st.cache_resource
def get_agent() -> ClinicGenieAppointmentAgent:
    return ClinicGenieAppointmentAgent()


def build_agent_messages():
    return [
        message_from_role(message["role"], message["content"])
        for message in st.session_state.messages
    ]


st.title("ClinicGenie Appointment Chatbot")
st.caption("Check availability, book, cancel, or reschedule doctor appointments.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hi, I can help you check availability, book, cancel, or "
                "reschedule a doctor's appointment. For booking changes, "
                "please include the doctor name, date/time, and your 7 or 8 "
                "digit patient ID."
            ),
        }
    ]

if st.sidebar.button("Clear chat"):
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Chat cleared. How can I help with your appointment?",
        }
    ]
    st.rerun()

with st.sidebar:
    st.subheader("Date format")
    st.write("Use `DD-MM-YYYY HH:MM`")
    st.subheader("Example")
    st.write("Is john doe available on 05-08-2024?")
    st.write("Book an appointment with john doe on 05-08-2024 08:00. My ID is 1234567.")

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
