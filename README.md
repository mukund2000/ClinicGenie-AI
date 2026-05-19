# ClinicGenie-AI System Architecture and Design

## Overview

ClinicGenie-AI is a doctor appointment system with two user-facing entry points:

1. A FastAPI HTTP API for patient onboarding, lookup, appointment booking, cancellation, rescheduling, availability checks (single day or date range), history, and chat.
2. A Streamlit chatbot UI that lets patients interact conversationally with the appointment agent.

Both paths are designed to use the same SQLite-backed service layer in `core/database.py`. This keeps appointment state consistent whether a request comes from an API client or from the AI chatbot tools.

### Key Features

- **Single-day availability**: Check availability for a specific doctor or specialization on a given date
- **Date range search**: Find all available doctors or a specific doctor's availability within a date range
- **Patient management**: Onboard, lookup, and update patient profiles
- **Appointment operations**: Book, cancel, and reschedule appointments
- **Conversation interface**: Natural language chatbot for appointment operations
- **REST API**: Full HTTP API for programmatic access
- **Observability**: Structured logging and metrics endpoints

## High-Level Architecture

```text
Client / Browser / API Consumer
        |
        v
FastAPI app
main.py
        |
        v
FastAPI controllers
controllers/
        |
        v
SQLite service layer
core/database.py
        |
        v
SQLite database
data/clinicgenie.db


Streamlit chatbot
client/streamlit_chatbot.py
        |
        v
LangGraph appointment agent
agent/appointment_agent.py
        |
        v
LangChain tools
toolkit/tools.py
        |
        v
SQLite service layer
core/database.py
        |
        v
SQLite database
data/clinicgenie.db
```

## Project Structure

```text
ClinicGenie-AI/
├── core/
│   ├── __init__.py
│   └── database.py              # SQLite service layer
├── agent/
│   ├── __init__.py
│   └── appointment_agent.py     # LangGraph/LangChain agent
├── controllers/
│   ├── __init__.py
│   ├── patient_controller.py
│   ├── appointment_chat_controller.py
│   ├── doctor_availability_controller.py
│   └── system_controller.py
├── client/
│   └── streamlit_chatbot.py     # Streamlit UI
├── data/
│   ├── clinicgenie.db
│   └── doctor_availability.csv
├── data_models/
│   └── models.py
├── toolkit/
│   └── tools.py                 # LangChain tools
├── main.py                      # FastAPI app
├── requirements.txt
└── README.md
```

## Main Components

### `main.py`

`main.py` defines the FastAPI application and registers the route controllers.

Responsibilities:

- Starts and initializes the database on app startup.
- Seeds appointment slots from `data/doctor_availability.csv` when the SQLite appointment table is empty.
- Registers API middleware, request logging, and routers from `controllers/`.
- Keeps app composition separate from endpoint handler code.

### `controllers/`

`controllers/` contains the FastAPI route groups. The controllers validate request payloads with Pydantic models, call the service layer or appointment agent, and map results to HTTP responses.

Controller files:

- `controllers/patient_controller.py`
  - Patient onboarding, lookup, updates, and patient history.
- `controllers/appointment_chat_controller.py`
  - Doctor catalog, appointment availability, booking, cancellation, rescheduling, appointment history, and chat.
- `controllers/doctor_availability_controller.py`
  - Doctor availability search by date range for all doctors and specific doctors.
- `controllers/system_controller.py`
  - Health, readiness, liveness, and metrics endpoints.

Important endpoint groups:

- Patient onboarding and lookup:
  - `POST /patients`
  - `GET /patients/lookup`
  - `GET /patients/by-email/{email}`
  - `GET /patients/by-phone/{phone}`
  - `GET /patients/{patient_id}`
  - `PATCH /patients/{patient_id}`

- Appointment operations:
  - `GET /doctors`
  - `GET /specializations`
  - `GET /catalog`
  - `GET /appointments/availability/doctor`
  - `GET /appointments/availability/specialization`
  - `POST /appointments/book`
  - `POST /appointments/cancel`
  - `POST /appointments/reschedule`
  - `GET /appointments/history/{patient_id}`

- Doctor availability by date range:
  - `POST /doctors/search-available` - Search all available doctors in a date range
  - `GET /doctors/{doctor_name}/search-available` - Search specific doctor's availability in date range

- Chat:
  - `POST /chat`

- Observability:
  - `GET /health`
  - `GET /health/live`
  - `GET /health/ready`
  - `GET /metrics`

### `core/database.py`

`core/database.py` is the main service and persistence layer. It owns all direct SQLite access.

Responsibilities:

- Creates and migrates database tables.
- Initializes the database only once per process, and recreates the schema if the SQLite file is missing.
- Opens SQLite connections with foreign key support enabled.
- Provides patient lookup functions by ID, email, phone, or combined contact details.
- Creates and updates patients.
- Creates appointment slots.
- Books, cancels, and reschedules appointments.
- Records appointment history for patient activity.
- Reads patient history.
- Seeds appointment slot data from CSV into SQLite.
- Searches for available doctors within a date range.

Important service functions:

- `get_patient(patient_id)`
- `get_patient_by_email(email)`
- `get_patient_by_phone(phone)`
- `get_patient_by_contact(email, phone)`
- `create_patient(...)`
- `update_patient(...)`
- `create_appointment(...)`
- `cancel_appointment(...)`
- `reschedule_appointment(...)`
- `get_patient_history(patient_id)`
- `get_available_slots_by_doctor(date, doctor_name)`
- `get_available_slots_by_specialization(date, specialization)`
- `search_doctors_by_date_range(start_date, end_date)` - Search all available doctors in date range
- `search_doctor_availability_by_name_and_date_range(doctor_name, start_date, end_date)` - Search specific doctor's availability
- `list_doctors()`
- `list_specializations()`

### `toolkit/tools.py`

`toolkit/tools.py` contains LangChain tools used by the appointment agent.

Responsibilities:

- Exposes appointment operations as tool-callable functions for the LLM.
- Exposes patient lookup, onboarding, and history retrieval as tool-callable functions for the LLM.
- Converts conversational tool inputs into service-layer calls.
- Uses `database.py` instead of directly editing CSV files.

This means chatbot bookings and API bookings update the same SQLite database.

Patient tools:

- `lookup_patient`
  - Looks up an existing patient by email or phone.
  - Calls `database.get_patient_by_contact()`.

- `onboard_patient`
  - Creates a new patient profile when lookup fails.
  - Requires patient name and at least one contact method.
  - Calls `database.create_patient()`.

- `retrieve_patient_history`
  - Retrieves patient appointment history after lookup identifies the patient ID.
  - Calls `database.get_patient_history()`.

Appointment tools:

- `check_availability_by_doctor` - Check doctor availability on a specific date
- `check_availability_by_specialization` - Check specialization availability on a specific date
- `search_doctors_by_date_range` - Search all available doctors within a date range
- `search_doctor_availability` - Search specific doctor's availability within a date range
- `set_appointment` - Book an appointment
- `cancel_appointment` - Cancel an appointment
- `reschedule_appointment` - Reschedule an appointment

### `agent/appointment_agent.py`

`agent/appointment_agent.py` defines the LangGraph-powered appointment assistant.

Responsibilities:

- Creates the LLM-backed appointment agent.
- Binds appointment tools from `toolkit/tools.py`.
- Binds patient lookup, onboarding, and history tools from `toolkit/tools.py`.
- Supports date range searches for doctor availability.
- Maintains the conversation flow:
  - user message
  - assistant reasoning
  - tool call if needed
  - final assistant response

The agent can check availability (single day or date range), book, cancel, and reschedule appointments when the user provides the required details.

The agent follows a contact-first patient workflow. For booking, cancellation, rescheduling, and history retrieval, it looks up the patient by email or phone before performing the appointment operation. If the patient does not exist and the user wants to book, it asks for the patient's name and missing contact details, onboards the patient, and then continues booking with the returned patient ID.

### `client/streamlit_chatbot.py`

`client/streamlit_chatbot.py` provides a local Streamlit console for chat, patient management, history, and booking.

Responsibilities:

- Displays chat history.
- Sends user messages to the `/chat` API endpoint.
- Shows the assistant response.
- Provides a patient registration form.
- Provides patient lookup by email or phone.
- Loads doctor options from the `/doctors` API endpoint.
- Stores the currently selected patient in Streamlit session state.
- Shows appointment history for the selected patient.
- Books appointments through the API with the selected patient context.

Boundaries:

- May call HTTP endpoints exposed by the FastAPI app in `main.py`.
- Must not import `core/database.py`, `toolkit/tools.py`, or `agent/appointment_agent.py`.
- Must not initialize or seed the database directly.

Run the API with:

```bash
uvicorn main:app --reload
```

## Database Design

The SQLite database is stored at:

```text
data/clinicgenie.db
```

### `patients`

Stores patient profile and contact information.

```text
id          INTEGER PRIMARY KEY AUTOINCREMENT
name        TEXT NOT NULL
email       TEXT UNIQUE
phone       TEXT UNIQUE
dob         TEXT
created_at  TEXT DEFAULT CURRENT_TIMESTAMP
```

Design notes:

- Email and phone are unique so the system can reliably look up existing patients.
- Either email or phone should be provided during onboarding.
- Existing CSV appointment patient IDs are imported as placeholder patients when needed.

### `appointments`

Stores appointment slots and their booking state.

```text
id                 INTEGER PRIMARY KEY AUTOINCREMENT
date_slot          TEXT NOT NULL
specialization     TEXT NOT NULL
doctor_name        TEXT NOT NULL
is_available       INTEGER NOT NULL DEFAULT 1
patient_to_attend  INTEGER REFERENCES patients(id)
```

Design notes:

- Each row represents one doctor appointment slot.
- `is_available = 1` means the slot can be booked.
- `is_available = 0` means the slot is booked.
- `patient_to_attend` points to the patient who booked the slot.
- `patient_to_attend` is normalized as a foreign key to `patients.id`.

### `appointment_history`

Stores patient activity history.

```text
id              INTEGER PRIMARY KEY AUTOINCREMENT
patient_id      INTEGER NOT NULL REFERENCES patients(id)
appointment_id  INTEGER REFERENCES appointments(id)
action          TEXT NOT NULL
details         TEXT
created_at      TEXT DEFAULT CURRENT_TIMESTAMP
```

Design notes:

- Booking, cancellation, and rescheduling events are stored here.
- History is patient-centered, so the UI/API can show a patient timeline.
- `appointment_id` links the history event to the relevant appointment row when possible.

## Request Flow

### Patient Onboarding

```text
POST /patients
        |
        v
controllers/patient_controller.py validates name/contact
        |
        v
database.create_patient()
        |
        v
patients row inserted
        |
        v
API returns created patient
```

### Patient Lookup

```text
GET /patients/lookup?email=...&phone=...
        |
        v
controllers/patient_controller.py receives query params
        |
        v
database.get_patient_by_contact()
        |
        v
API returns patient or 404
```

### Appointment Booking

```text
POST /appointments/book
        |
        v
controllers/appointment_chat_controller.py validates patient_id, doctor_name, date_slot
        |
        v
database.create_appointment()
        |
        v
Checks patient exists
        |
        v
Checks requested slot is available
        |
        v
Marks slot unavailable and stores patient_to_attend
        |
        v
Writes appointment_history action = booked
        |
        v
API returns booked appointment
```

### Chatbot Appointment Booking

```text
User asks to book an appointment
        |
        v
Agent checks required details:
doctor, appointment date/time, email or phone
        |
        v
Agent calls lookup_patient
        |
        v
If patient exists, tool returns patient ID
        |
        v
Agent calls set_appointment using patient ID
        |
        v
database.create_appointment() books the slot
        |
        v
appointment_history stores action = booked
        |
        v
Agent explains booking result to user
```

If lookup fails:

```text
lookup_patient returns no patient found
        |
        v
Agent asks for missing onboarding details
        |
        v
Agent calls onboard_patient
        |
        v
database.create_patient() creates patient
        |
        v
Agent uses returned patient ID
        |
        v
Agent calls set_appointment
```

### Appointment Cancellation

```text
POST /appointments/cancel
        |
        v
database.cancel_appointment()
        |
        v
Finds booked slot for patient, doctor, and date
        |
        v
Marks slot available and clears patient_to_attend
        |
        v
Writes appointment_history action = cancelled
        |
        v
API returns updated appointment
```

### Appointment Rescheduling

```text
POST /appointments/reschedule
        |
        v
database.reschedule_appointment()
        |
        v
Finds existing booked appointment
        |
        v
Finds requested new available slot
        |
        v
Frees old slot
        |
        v
Books new slot
        |
        v
Writes appointment_history action = rescheduled
        |
        v
API returns new booked appointment
```

### Chatbot Flow

```text
User message
        |
        v
streamlit_chatbot.py or POST /chat
        |
        v
ClinicGenieAppointmentAgent
        |
        v
LLM decides whether a tool is required
        |
        v
toolkit/tools.py
        |
        v
database.py service function
        |
        v
SQLite update/read
        |
        v
Tool result returned to agent
        |
        v
Final assistant response returned to user
```

For patient-specific operations, the chatbot flow includes contact lookup before appointment mutation:

```text
User requests booking/cancellation/reschedule/history
        |
        v
Agent asks for email or phone if missing
        |
        v
lookup_patient tool
        |
        v
database.get_patient_by_contact()
        |
        v
Patient ID returned to agent
        |
        v
Agent calls appointment or history tool
```

## API Design

The API is intentionally thin. It validates input, calls service functions, and maps service results to HTTP responses.

This keeps business rules in one place:

```text
main.py                                  FastAPI app composition
controllers/*.py                         HTTP route handlers
database.py                              business logic and persistence
toolkit/tools.py                         chatbot adapters to business logic
```

This design prevents duplicate appointment behavior between the chatbot and API.

The chatbot and API share the same backend service layer:

```text
FastAPI endpoint -> database.py
Agent tool       -> database.py
```

This is important because patient lookup, onboarding, booking, cancellation, rescheduling, and history all update or read the same SQLite database.

## Error Handling Strategy

Common API responses:

- `400 Bad Request`
  - Missing required contact details during patient creation.

- `404 Not Found`
  - Patient does not exist.
  - Appointment to cancel does not exist.

- `409 Conflict`
  - Duplicate email or phone.
  - Requested booking slot is unavailable.
  - Existing appointment for reschedule was not found.
  - New reschedule slot is unavailable.

The chatbot tools return user-readable messages instead of HTTP status codes. For example:

- No patient found for that contact.
- Patient onboarded successfully.
- No available appointments for that particular case.
- Successfully cancelled.
- No appointment history found for this patient.

## Data Consistency

Booking, cancellation, rescheduling, and history writes are handled in database transactions through the `db_connection()` context manager.

If an operation fails, the transaction is rolled back. This prevents partial updates such as booking a slot without recording history.

SQLite foreign keys are enabled for every connection:

```python
connection.execute("PRAGMA foreign_keys = ON")
```

This ensures `appointments.patient_to_attend` and `appointment_history.patient_id` reference real patients.

## Seeding Strategy

The original appointment availability data lives in:

```text
data/doctor_availability.csv
```

On API startup:

1. The database schema is initialized.
2. The API checks whether the `appointments` table is empty.
3. If empty, appointment slots are imported from the CSV file.

This gives the SQLite backend a starting set of doctor availability records while allowing all future changes to happen in SQLite.

The service layer also has a lightweight guard, `ensure_database_initialized()`, used by database functions. It does not rebuild the schema on every call. It only calls `initialize_database()` if the process has not initialized the database yet, or if `data/clinicgenie.db` no longer exists.

## Running the System

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn main:app --reload
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

Run the Streamlit chatbot:

```bash
streamlit run client/streamlit_chatbot.py
```

### Run API and UI Together

Open two terminals from the `ClinicGenie-AI` folder.

Terminal 1, API:

```bash
uvicorn main:app --reload
```

Terminal 2, UI:

```bash
$env:CLINICGENIE_API_BASE_URL="http://127.0.0.1:8000"
streamlit run client/streamlit_chatbot.py
```

The Streamlit app expects the FastAPI server at `http://127.0.0.1:8000` by default. Override it with:

```bash
$env:CLINICGENIE_API_BASE_URL="http://127.0.0.1:8000"
streamlit run client/streamlit_chatbot.py
```

Doctor and specialization values are loaded from the appointment database through the API. Updating seeded appointment data changes the catalog without editing `toolkit/tools.py`, `agent/appointment_agent.py`, or `client/streamlit_chatbot.py`.

Observability endpoints:

```text
http://127.0.0.1:8000/health/live
http://127.0.0.1:8000/health/ready
http://127.0.0.1:8000/metrics
```

Logs are structured JSON by default and include API request timing, DB operation timing, agent invocation timing, and tool call timing. Configure the log level with:

```bash
$env:CLINICGENIE_LOG_LEVEL="INFO"
```

## Example API Calls

### Create a patient

```bash
curl -X POST http://127.0.0.1:8000/patients \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Asha Rao\",\"email\":\"asha@example.com\",\"phone\":\"9999999999\",\"dob\":\"1995-04-10\"}"
```

### Look up a patient

```bash
curl "http://127.0.0.1:8000/patients/lookup?email=asha@example.com"
```

### Check doctor availability by date range

```bash
curl -X POST http://127.0.0.1:8000/doctors/search-available \
  -H "Content-Type: application/json" \
  -d "{\"start_date\":\"05-08-2024\",\"end_date\":\"10-08-2024\"}"
```

### Check specific doctor availability by date range

```bash
curl "http://127.0.0.1:8000/doctors/john%20doe/search-available?start_date=05-08-2024&end_date=10-08-2024"
```

### Book an appointment

```bash
curl -X POST http://127.0.0.1:8000/appointments/book \
  -H "Content-Type: application/json" \
  -d "{\"patient_id\":1234567,\"doctor_name\":\"john doe\",\"date_slot\":\"05-08-2024 08:00\"}"
```

### Cancel an appointment

```bash
curl -X POST http://127.0.0.1:8000/appointments/cancel \
  -H "Content-Type: application/json" \
  -d "{\"patient_id\":1234567,\"doctor_name\":\"john doe\",\"date_slot\":\"05-08-2024 08:00\"}"
```

### Reschedule an appointment

```bash
curl -X POST http://127.0.0.1:8000/appointments/reschedule \
  -H "Content-Type: application/json" \
  -d "{\"patient_id\":1234567,\"doctor_name\":\"john doe\",\"old_date_slot\":\"05-08-2024 08:00\",\"new_date_slot\":\"07-08-2024 08:30\"}"
```

### Ask the chatbot through the API

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Is john doe available on 05-08-2024?\"}"
```

## Future Improvements

- Add authentication and authorization for staff/admin users.
- Add patient identity verification before appointment changes.
- Store dates in ISO format instead of `DD-MM-YYYY HH:MM`.
- Add doctors as a dedicated database table.
- Add specializations as a dedicated database table.
- Add automated tests for service and API behavior.
- Add structured response models for all API endpoints.
- Add pagination for appointment history.
- Replace global agent initialization with dependency injection if the app grows.
