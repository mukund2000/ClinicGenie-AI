
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from toolkit.tools import *

load_dotenv()

# Base LLM instance (no tools attached yet)
llm=ChatGroq(model_name="openai/gpt-oss-20b")

llm_with_tools = llm.bind_tools([check_availability_by_doctor, check_availability_by_specialization, set_appointment, cancel_appointment, reschedule_appointment])

response = llm_with_tools.invoke([
    SystemMessage(content="You are a medical assistant. If user asks about doctor availability, you MUST call the tool."),
    HumanMessage(content="reschedule my appointment with a dr. john doe from 5-8-2024 08:00 to 7-8-2024 8:30? My id number is 1234567`")
])
print(response)


if response.tool_calls:
    tool_call = response.tool_calls[0]
    tool_result = reschedule_appointment.invoke(tool_call["args"])
    print("Tool Output:", tool_result)