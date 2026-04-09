
from typing import Literal
from data_models.models import *
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import pandas as pd
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

# Base LLM instance (no tools attached yet)
llm=ChatGroq(model_name="openai/gpt-oss-20b")

    

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

@tool
def cancel_appointment(date:DateTimeModel, id_number:IdentificationNumberModel, doctor_name:Literal['kevin anderson','robert martinez','susan davis','daniel miller','sarah wilson','michael green','lisa brown','jane smith','emily johnson','john doe']):
    """
    Canceling an appointment.
    The parameters MUST be mentioned by the user in the query.
    """
    df = pd.read_csv(r"C:\Users\mukun\OneDrive\Documents\Projects\doctor-appointment\ClinicGenie-AI\data\availability.csv")
    print(f"Cancelling appointment for doctor {doctor_name} on {date.date} for patient with ID {id_number.id}")
    case_to_remove = df[(df['date_slot'] == date.date)&(df['patient_to_attend'] == id_number.id)&(df['doctor_name'] == doctor_name)]
    if len(case_to_remove) == 0:
        return "You don´t have any appointment with that specifications"
    else:
        df.loc[(df['date_slot'] == date.date) & (df['patient_to_attend'] == id_number.id) & (df['doctor_name'] == doctor_name), ['is_available', 'patient_to_attend']] = [True, None]
        df.to_csv(r"C:\Users\mukun\OneDrive\Documents\Projects\doctor-appointment\ClinicGenie-AI\data\availability.csv", index = False)

        return "Successfully cancelled"

llm_with_tools = llm.bind_tools([check_availability_by_doctor, check_availability_by_specialization, set_appointment, cancel_appointment])

response = llm_with_tools.invoke([
    SystemMessage(content="You are a medical assistant. If user asks about doctor availability, you MUST call the tool."),
    HumanMessage(content="book my appointment with a dr. john doe on 5-8-2024 08:00? My id number is 1234567`")
])
print(response)


if response.tool_calls:
    tool_call = response.tool_calls[0]
    tool_result = set_appointment.invoke(tool_call["args"])
    print("Tool Output:", tool_result)