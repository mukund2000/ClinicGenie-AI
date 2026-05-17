from typing import Annotated, Any, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from toolkit.tools import (
    cancel_appointment,
    check_availability_by_doctor,
    check_availability_by_specialization,
    lookup_patient,
    onboard_patient,
    retrieve_patient_history,
    reschedule_appointment,
    set_appointment,
)


load_dotenv()


class AppointmentAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


BOOKING_AGENT_PROMPT = """
You are ClinicGenie, a doctor appointment assistant.

You can help patients check doctor availability, book appointments, cancel
appointments, reschedule appointments, onboard patients, look up existing
patients, and retrieve patient appointment history by using the available tools.

Available doctors:
- kevin anderson
- robert martinez
- susan davis
- daniel miller
- sarah wilson
- michael green
- lisa brown
- jane smith
- emily johnson
- john doe

Required information:
- To check availability by doctor: doctor name and date.
- To check availability by specialization: specialization and date.
- To look up a patient: email or phone number.
- To onboard a patient: name and at least one contact method, email or phone.
- To retrieve patient history: first look up the patient by email or phone, then use the patient ID.
- To book: doctor name, appointment date/time, and patient email or phone for lookup.
- To cancel: doctor name, existing appointment date/time, and patient email or phone for lookup.
- To reschedule: doctor name, old appointment date/time, new appointment date/time, and patient email or phone for lookup.

Patient workflow rules:
- Before booking, cancelling, rescheduling, or retrieving history, first use lookup_patient with the patient's email or phone.
- If lookup_patient returns an existing patient, use that patient's ID for booking, cancellation, rescheduling, or history.
- If booking is requested and no patient is found, ask for the patient's name and missing contact details, then use onboard_patient.
- After onboarding, use the returned patient ID for booking.
- Do not ask the user for a patient ID unless they cannot provide email or phone.
- Do not book an appointment for an unknown patient.

Formatting rules:
- Use DD-MM-YYYY for availability dates.
- Use DD-MM-YYYY HH:MM for appointment date/time.
- Patient ID must be 7 or 8 digits when a patient ID is required by a tool.
- Doctor names must be lowercase and must match one of the listed doctor names.

If any required detail is missing or ambiguous, ask one short follow-up question.
Do not call a tool until you have all required details.
After a tool call, explain the result clearly to the patient.
"""


class ClinicGenieAppointmentAgent:
    def __init__(self, model_name: str = "openai/gpt-oss-20b"):
        self.tools = [
            check_availability_by_doctor,
            check_availability_by_specialization,
            lookup_patient,
            onboard_patient,
            retrieve_patient_history,
            set_appointment,
            cancel_appointment,
            reschedule_appointment,
        ]
        self.llm = ChatGroq(model_name=model_name).bind_tools(self.tools)
        self.graph = self._build_graph()

    def _assistant_node(self, state: AppointmentAgentState) -> dict[str, Any]:
        messages = [SystemMessage(content=BOOKING_AGENT_PROMPT)] + state["messages"]
        response = self.llm.invoke(messages)
        return {"messages": [response]}

    def _build_graph(self):
        graph = StateGraph(AppointmentAgentState)
        graph.add_node("assistant", self._assistant_node)
        graph.add_node("tools", ToolNode(self.tools))

        graph.add_edge(START, "assistant")
        graph.add_conditional_edges(
            "assistant",
            tools_condition,
            {
                "tools": "tools",
                END: END,
            },
        )
        graph.add_edge("tools", "assistant")

        return graph.compile()

    def invoke_messages(
        self, messages: list[BaseMessage], config: Optional[dict[str, Any]] = None
    ) -> list[BaseMessage]:
        result = self.graph.invoke(
            {"messages": messages},
            config=config,
        )
        return result["messages"]

    def invoke(self, user_query: str, config: Optional[dict[str, Any]] = None) -> BaseMessage:
        result = self.invoke_messages(
            [HumanMessage(content=user_query)],
            config=config,
        )
        return result[-1]


def message_from_role(role: str, content: str) -> BaseMessage:
    if role == "assistant":
        return AIMessage(content=content)
    return HumanMessage(content=content)


if __name__ == "__main__":
    agent = ClinicGenieAppointmentAgent()
    answer = agent.invoke(
        "Book an appointment with john doe on 05-08-2024 08:00. My email is asha@example.com."
    )
    print(answer.content)
