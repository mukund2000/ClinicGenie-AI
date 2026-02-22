
import re
from typing import Literal

from dotenv import load_dotenv
from langchain_groq import ChatGroq
import pandas as pd
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

# Base LLM instance (no tools attached yet)
llm=ChatGroq(model_name="openai/gpt-oss-20b")

class DateModel(BaseModel):
    date: str = Field(description="Properly formatted date", pattern=r'^\d{2}-\d{2}-\d{4}$')
    @field_validator("date")
    def check_format_date(cls, v):
        if not re.match(r'^\d{2}-\d{2}-\d{4}$', v):  # Ensures DD-MM-YYYY format
            raise ValueError("The date must be in the format 'DD-MM-YYYY'")
        return v
    

@tool
def check_availability_by_doctor(desired_date:DateModel, doctor_name:Literal['kevin anderson','robert martinez','susan davis','daniel miller','sarah wilson','michael green','lisa brown','jane smith','emily johnson','john doe']):
    """
    Checking the database if we have availability for the specific doctor.
    The parameters should be mentioned by the user in the query
    """
    print(f"Checking availability for doctor {doctor_name} on {desired_date.date}")
    df = pd.read_csv(r"C:\Users\mukun\OneDrive\Documents\Projects\doctor-appointment\project\data\doctor_availability.csv")
    
    print(df.head())
    
    df['date_slot_time'] = df['date_slot'].apply(lambda input: input.split(' ')[-1])
    
    rows = list(df[(df['date_slot'].apply(lambda input: input.split(' ')[0]) == desired_date.date)&(df['doctor_name'] == doctor_name)&(df['is_available'] == True)]['date_slot_time'])

    if len(rows) == 0:
        output = "No availability in the entire day"
    else:
        output = f'This availability for {desired_date.date}\n'
        output += "Available slots: " + ', '.join(rows)

    return output

llm_with_tools = llm.bind_tools([check_availability_by_doctor])

response = llm_with_tools.invoke([
    SystemMessage(content="You are a medical assistant. If user asks about doctor availability, you MUST call the tool."),
    HumanMessage(content="What are the available slots for doctor kevin anderson on 7-8-2024?")
])
print(response)


if response.tool_calls:
    tool_call = response.tool_calls[0]
    tool_result = check_availability_by_doctor.invoke(tool_call["args"])
    print("Tool Output:", tool_result)