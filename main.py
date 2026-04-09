
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
    
class DateTimeModel(BaseModel):
    date:str=Field(description="Properly formatted date", pattern=r'^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$')
    
    @field_validator("date")
    def check_format_date(cls, v):
        if not re.match(r'^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$', v):  # Ensures 'DD-MM-YYYY HH:MM' format
            raise ValueError("The date should be in format 'DD-MM-YYYY HH:MM'")
        return v
    
class IdentificationNumberModel(BaseModel):
    id: int = Field(description="Identification number (7 or 8 digits long)")
    @field_validator("id")
    def check_format_id(cls, v):
        if not re.match(r'^\d{7,8}$', str(v)):  # Convert to string before matching
            raise ValueError("The ID number should be a 7 or 8-digit number")
        return v
    

@tool
def check_availability_by_doctor(desired_date:DateModel, doctor_name:Literal['kevin anderson','robert martinez','susan davis','daniel miller','sarah wilson','michael green','lisa brown','jane smith','emily johnson','john doe']):
    """
    Checking the database if we have availability for the specific doctor.
    The parameters should be mentioned by the user in the query
    """
    print(f"Checking availability for doctor {doctor_name} on {desired_date.date}")
    df = pd.read_csv(r"C:\Users\mukun\OneDrive\Documents\Projects\doctor-appointment\ClinicGenie-AI\data\doctor_availability.csv")
    
    print(df.head())
    
    df['date_slot_time'] = df['date_slot'].apply(lambda input: input.split(' ')[-1])
    
    rows = list(df[(df['date_slot'].apply(lambda input: input.split(' ')[0]) == desired_date.date)&(df['doctor_name'] == doctor_name)&(df['is_available'] == True)]['date_slot_time'])

    if len(rows) == 0:
        output = "No availability in the entire day"
    else:
        output = f'This availability for {desired_date.date}\n'
        output += "Available slots: " + ', '.join(rows)

    return output

@tool
def check_availability_by_specialization(desired_date:DateModel, specialization:Literal["general_dentist", "cosmetic_dentist", "prosthodontist", "pediatric_dentist","emergency_dentist","oral_surgeon","orthodontist"]):
    """
    Checking the database if we have availability for the specific specialization.
    The parameters should be mentioned by the user in the query
    """
    df = pd.read_csv(r"C:\Users\mukun\OneDrive\Documents\Projects\doctor-appointment\ClinicGenie-AI\data\doctor_availability.csv")
    df['date_slot_time'] = df['date_slot'].apply(lambda input: input.split(' ')[-1])
    rows = df[(df['date_slot'].apply(lambda input: input.split(' ')[0]) == desired_date.date) & (df['specialization'] == specialization) & (df['is_available'] == True)].groupby(['specialization', 'doctor_name'])['date_slot_time'].apply(list).reset_index(name='available_slots')
    print("rows:",rows)
    if len(rows) == 0:
        output = "No availability in the entire day"
    else:
        def convert_to_am_pm(time_str):
            # Split the time string into hours and minutes
            time_str = str(time_str)
            hours, minutes = map(int, time_str.split(":"))
            
            # Determine AM or PM
            period = "AM" if hours < 12 else "PM"
            
            # Convert hours to 12-hour format
            hours = hours % 12 or 12
            
            # Format the output
            return f"{hours}:{minutes:02d} {period}"
        output = f'This availability for {desired_date.date}\n'
        for row in rows.values:
            output += row[1] + ". Available slots: \n" + ', \n'.join([convert_to_am_pm(value)for value in row[2]])+'\n'

    return output

@tool
def set_appointment(desired_date:DateTimeModel, id_number:IdentificationNumberModel, doctor_name:Literal['kevin anderson','robert martinez','susan davis','daniel miller','sarah wilson','michael green','lisa brown','jane smith','emily johnson','john doe']):
    """
    Set appointment or slot with the doctor.
    The parameters MUST be mentioned by the user in the query.
    """
    df = pd.read_csv(r"C:\Users\mukun\OneDrive\Documents\Projects\doctor-appointment\ClinicGenie-AI\data\doctor_availability.csv")

    print(f"Setting appointment for doctor {doctor_name} on {desired_date.date} for patient with ID {id_number.id}")
    case = df[(df['date_slot'] == desired_date.date)&(df['doctor_name'] == doctor_name)&(df['is_available'] == True)]
    if len(case) == 0:
        return "No available appointments for that particular case"
    else:
        df.loc[(df['date_slot'] == (desired_date.date))&(df['doctor_name'] == doctor_name) & (df['is_available'] == True), ['is_available','patient_to_attend']] = [False, id_number.id]
        df.to_csv(r"C:\Users\mukun\OneDrive\Documents\Projects\doctor-appointment\ClinicGenie-AI\data\availability.csv", index = False)

        return "Successfully done"



llm_with_tools = llm.bind_tools([check_availability_by_doctor, check_availability_by_specialization, set_appointment])

response = llm_with_tools.invoke([
    SystemMessage(content="You are a medical assistant. If user asks about doctor availability, you MUST call the tool."),
    HumanMessage(content="book my appointment with a dr. john doe on 5-8-2024 08:00? My id number is 1234567`")
])
print(response)


if response.tool_calls:
    tool_call = response.tool_calls[0]
    tool_result = set_appointment.invoke(tool_call["args"])
    print("Tool Output:", tool_result)