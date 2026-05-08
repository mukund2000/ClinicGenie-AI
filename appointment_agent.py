from typing import Annotated, Any, Optional

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from toolkit.tools import cancel_appointment, reschedule_appointment, set_appointment


load_dotenv()


class AppointmentAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


BOOKING_AGENT_PROMPT = """
You are ClinicGenie, a doctor appointment assistant.

You can help patients book, cancel, and reschedule doctor appointments by using
the available tools.

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
- To book: doctor name, patient ID number, and appointment date/time.
- To cancel: doctor name, patient ID number, and existing appointment date/time.
- To reschedule: doctor name, patient ID number, old appointment date/time, and new appointment date/time.

Formatting rules:
- Use DD-MM-YYYY HH:MM for appointment date/time.
- Patient ID must be 7 or 8 digits.
- Doctor names must be lowercase and must match one of the listed doctor names.

If any required detail is missing or ambiguous, ask one short follow-up question.
Do not call a tool until you have all required details.
After a tool call, explain the result clearly to the patient.
"""


class ClinicGenieAppointmentAgent:
    def __init__(self, model_name: str = "openai/gpt-oss-20b"):
        self.tools = [set_appointment, cancel_appointment, reschedule_appointment]
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

    def invoke(self, user_query: str, config: Optional[dict[str, Any]] = None) -> BaseMessage:
        result = self.graph.invoke(
            {"messages": [HumanMessage(content=user_query)]},
            config=config,
        )
        return result["messages"][-1]


if __name__ == "__main__":
    agent = ClinicGenieAppointmentAgent()
    answer = agent.invoke(
        "Book an appointment with john doe on 05-08-2024 08:00. My ID is 1234567."
    )
    print(answer.content)
