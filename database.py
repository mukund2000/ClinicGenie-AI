# Run this script to initialize the database and seed it with doctor availability data from the CSV file.

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from observability import observe_operation


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "clinicgenie.db"
DOCTOR_AVAILABILITY_CSV = DATA_DIR / "doctor_availability.csv"
_DATABASE_INITIALIZED = False


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@observe_operation(layer="db", logger_name=__name__)
def initialize_database() -> None:
    global _DATABASE_INITIALIZED
    if _DATABASE_INITIALIZED and DATABASE_PATH.exists():
        return

    with db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                phone TEXT UNIQUE,
                dob TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_appointments_schema(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS appointment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                appointment_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (patient_id) REFERENCES patients(id),
                FOREIGN KEY (appointment_id) REFERENCES appointments(id)
            )
            """
        )
    _DATABASE_INITIALIZED = True


@observe_operation(layer="db", logger_name=__name__)
def ensure_database_initialized() -> None:
    if not _DATABASE_INITIALIZED or not DATABASE_PATH.exists():
        initialize_database()


def _ensure_appointments_schema(connection: sqlite3.Connection) -> None:
    table = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'appointments'
        """
    ).fetchone()

    if table is None:
        connection.execute(
            """
            CREATE TABLE appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_slot TEXT NOT NULL,
                specialization TEXT NOT NULL,
                doctor_name TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                patient_to_attend INTEGER,
                FOREIGN KEY (patient_to_attend) REFERENCES patients(id)
            )
            """
        )
        return

    foreign_keys = connection.execute("PRAGMA foreign_key_list(appointments)").fetchall()
    if any(row["from"] == "patient_to_attend" for row in foreign_keys):
        return

    rows = connection.execute(
        """
        SELECT id, date_slot, specialization, doctor_name, is_available, patient_to_attend
        FROM appointments
        """
    ).fetchall()

    patient_ids = {
        int(row["patient_to_attend"])
        for row in rows
        if row["patient_to_attend"] is not None
    }
    for patient_id in patient_ids:
        connection.execute(
            """
            INSERT OR IGNORE INTO patients (id, name)
            VALUES (?, ?)
            """,
            (patient_id, f"Imported Patient {patient_id}"),
        )

    connection.execute("ALTER TABLE appointments RENAME TO appointments_old")
    connection.execute(
        """
        CREATE TABLE appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_slot TEXT NOT NULL,
            specialization TEXT NOT NULL,
            doctor_name TEXT NOT NULL,
            is_available INTEGER NOT NULL DEFAULT 1,
            patient_to_attend INTEGER,
            FOREIGN KEY (patient_to_attend) REFERENCES patients(id)
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO appointments (
            id,
            date_slot,
            specialization,
            doctor_name,
            is_available,
            patient_to_attend
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["id"],
                row["date_slot"],
                row["specialization"],
                row["doctor_name"],
                row["is_available"],
                row["patient_to_attend"],
            )
            for row in rows
        ],
    )
    connection.execute("DROP TABLE appointments_old")


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


@observe_operation(layer="db", logger_name=__name__)
def get_patient(patient_id: int) -> Optional[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
    return _row_to_dict(row)


@observe_operation(layer="db", logger_name=__name__)
def get_patient_by_email(email: str) -> Optional[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM patients WHERE lower(email) = lower(?)",
            (email,),
        ).fetchone()
    return _row_to_dict(row)


@observe_operation(layer="db", logger_name=__name__)
def get_patient_by_phone(phone: str) -> Optional[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM patients WHERE phone = ?",
            (phone,),
        ).fetchone()
    return _row_to_dict(row)


@observe_operation(layer="db", logger_name=__name__)
def get_patient_by_contact(
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    ensure_database_initialized()
    if not email and not phone:
        return None

    clauses: list[str] = []
    params: list[str] = []
    if email:
        clauses.append("lower(email) = lower(?)")
        params.append(email)
    if phone:
        clauses.append("phone = ?")
        params.append(phone)

    with db_connection() as connection:
        row = connection.execute(
            f"SELECT * FROM patients WHERE {' OR '.join(clauses)} LIMIT 1",
            params,
        ).fetchone()
    return _row_to_dict(row)


@observe_operation(layer="db", logger_name=__name__)
def create_patient(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    dob: Optional[str] = None,
) -> dict[str, Any]:
    ensure_database_initialized()
    with db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO patients (name, email, phone, dob)
            VALUES (?, ?, ?, ?)
            """,
            (name, email, phone, dob),
        )
        row = connection.execute(
            "SELECT * FROM patients WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    patient = _row_to_dict(row)
    if patient is None:
        raise RuntimeError("Patient creation failed")
    return patient


@observe_operation(layer="db", logger_name=__name__)
def update_patient(
    patient_id: int,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    dob: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    ensure_database_initialized()
    fields = {
        "name": name,
        "email": email,
        "phone": phone,
        "dob": dob,
    }
    updates = [(key, value) for key, value in fields.items() if value is not None]
    if not updates:
        return get_patient(patient_id)

    assignments = ", ".join(f"{key} = ?" for key, _ in updates)
    params = [value for _, value in updates] + [patient_id]
    with db_connection() as connection:
        connection.execute(
            f"UPDATE patients SET {assignments} WHERE id = ?",
            params,
        )
        row = connection.execute(
            "SELECT * FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
    return _row_to_dict(row)


@observe_operation(layer="db", logger_name=__name__)
def record_patient_history(
    patient_id: int,
    action: str,
    appointment_id: Optional[int] = None,
    details: Optional[str] = None,
) -> dict[str, Any]:
    ensure_database_initialized()
    with db_connection() as connection:
        row = _record_patient_history(
            connection,
            patient_id=patient_id,
            action=action,
            appointment_id=appointment_id,
            details=details,
        )
    history = _row_to_dict(row)
    if history is None:
        raise RuntimeError("Patient history creation failed")
    return history


def _record_patient_history(
    connection: sqlite3.Connection,
    patient_id: int,
    action: str,
    appointment_id: Optional[int] = None,
    details: Optional[str] = None,
) -> sqlite3.Row:
    cursor = connection.execute(
        """
        INSERT INTO appointment_history (
            patient_id,
            appointment_id,
            action,
            details
        )
        VALUES (?, ?, ?, ?)
        """,
        (patient_id, appointment_id, action, details),
    )
    return connection.execute(
        "SELECT * FROM appointment_history WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()


@observe_operation(layer="db", logger_name=__name__)
def create_appointment_slot(
    date_slot: str,
    specialization: str,
    doctor_name: str,
    is_available: bool = True,
    patient_to_attend: Optional[int] = None,
) -> dict[str, Any]:
    ensure_database_initialized()
    with db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO appointments (
                date_slot,
                specialization,
                doctor_name,
                is_available,
                patient_to_attend
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                date_slot,
                specialization,
                doctor_name,
                int(is_available),
                patient_to_attend,
            ),
        )
        row = connection.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    appointment = _row_to_dict(row)
    if appointment is None:
        raise RuntimeError("Appointment slot creation failed")
    return appointment


@observe_operation(layer="db", logger_name=__name__)
def get_available_slots_by_doctor(date: str, doctor_name: str) -> list[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM appointments
            WHERE substr(date_slot, 1, 10) = ?
              AND lower(doctor_name) = lower(?)
              AND is_available = 1
            ORDER BY date_slot
            """,
            (date, doctor_name),
        ).fetchall()
    return _rows_to_dicts(rows)


@observe_operation(layer="db", logger_name=__name__)
def get_available_slots_by_specialization(
    date: str,
    specialization: str,
) -> list[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM appointments
            WHERE substr(date_slot, 1, 10) = ?
              AND lower(specialization) = lower(?)
              AND is_available = 1
            ORDER BY doctor_name, date_slot
            """,
            (date, specialization),
        ).fetchall()
    return _rows_to_dicts(rows)


@observe_operation(layer="db", logger_name=__name__)
def list_doctors() -> list[str]:
    ensure_database_initialized()
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT doctor_name
            FROM appointments
            WHERE doctor_name IS NOT NULL
              AND trim(doctor_name) != ''
            ORDER BY lower(doctor_name)
            """
        ).fetchall()
    return [str(row["doctor_name"]) for row in rows]


@observe_operation(layer="db", logger_name=__name__)
def list_specializations() -> list[str]:
    ensure_database_initialized()
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT specialization
            FROM appointments
            WHERE specialization IS NOT NULL
              AND trim(specialization) != ''
            ORDER BY lower(specialization)
            """
        ).fetchall()
    return [str(row["specialization"]) for row in rows]


@observe_operation(layer="db", logger_name=__name__)
def create_appointment(
    patient_id: int,
    doctor_name: str,
    date_slot: str,
) -> Optional[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        patient = connection.execute(
            "SELECT id FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
        if patient is None:
            return None

        appointment = connection.execute(
            """
            SELECT *
            FROM appointments
            WHERE date_slot = ?
              AND lower(doctor_name) = lower(?)
              AND is_available = 1
            LIMIT 1
            """,
            (date_slot, doctor_name),
        ).fetchone()
        if appointment is None:
            return None

        connection.execute(
            """
            UPDATE appointments
            SET is_available = 0,
                patient_to_attend = ?
            WHERE id = ?
            """,
            (patient_id, appointment["id"]),
        )
        _record_patient_history(
            connection,
            patient_id=patient_id,
            appointment_id=appointment["id"],
            action="booked",
            details=f"Booked {appointment['doctor_name']} on {appointment['date_slot']}",
        )
        row = connection.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (appointment["id"],),
        ).fetchone()
    return _row_to_dict(row)


@observe_operation(layer="db", logger_name=__name__)
def cancel_appointment(
    patient_id: int,
    doctor_name: str,
    date_slot: str,
) -> Optional[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        appointment = connection.execute(
            """
            SELECT *
            FROM appointments
            WHERE date_slot = ?
              AND lower(doctor_name) = lower(?)
              AND patient_to_attend = ?
              AND is_available = 0
            LIMIT 1
            """,
            (date_slot, doctor_name, patient_id),
        ).fetchone()
        if appointment is None:
            return None

        connection.execute(
            """
            UPDATE appointments
            SET is_available = 1,
                patient_to_attend = NULL
            WHERE id = ?
            """,
            (appointment["id"],),
        )
        _record_patient_history(
            connection,
            patient_id=patient_id,
            appointment_id=appointment["id"],
            action="cancelled",
            details=f"Cancelled {appointment['doctor_name']} on {appointment['date_slot']}",
        )
        row = connection.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (appointment["id"],),
        ).fetchone()
    return _row_to_dict(row)


@observe_operation(layer="db", logger_name=__name__)
def reschedule_appointment(
    patient_id: int,
    doctor_name: str,
    old_date_slot: str,
    new_date_slot: str,
) -> Optional[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        current = connection.execute(
            """
            SELECT *
            FROM appointments
            WHERE date_slot = ?
              AND lower(doctor_name) = lower(?)
              AND patient_to_attend = ?
              AND is_available = 0
            LIMIT 1
            """,
            (old_date_slot, doctor_name, patient_id),
        ).fetchone()
        target = connection.execute(
            """
            SELECT *
            FROM appointments
            WHERE date_slot = ?
              AND lower(doctor_name) = lower(?)
              AND is_available = 1
            LIMIT 1
            """,
            (new_date_slot, doctor_name),
        ).fetchone()
        if current is None or target is None:
            return None

        connection.execute(
            """
            UPDATE appointments
            SET is_available = 1,
                patient_to_attend = NULL
            WHERE id = ?
            """,
            (current["id"],),
        )
        connection.execute(
            """
            UPDATE appointments
            SET is_available = 0,
                patient_to_attend = ?
            WHERE id = ?
            """,
            (patient_id, target["id"]),
        )
        _record_patient_history(
            connection,
            patient_id=patient_id,
            appointment_id=target["id"],
            action="rescheduled",
            details=(
                f"Rescheduled {target['doctor_name']} from "
                f"{current['date_slot']} to {target['date_slot']}"
            ),
        )
        row = connection.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (target["id"],),
        ).fetchone()
    return _row_to_dict(row)


@observe_operation(layer="db", logger_name=__name__)
def get_patient_history(patient_id: int) -> list[dict[str, Any]]:
    ensure_database_initialized()
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                h.id,
                h.patient_id,
                h.appointment_id,
                h.action,
                h.details,
                h.created_at,
                a.date_slot,
                a.specialization,
                a.doctor_name
            FROM appointment_history h
            LEFT JOIN appointments a ON a.id = h.appointment_id
            WHERE h.patient_id = ?
            ORDER BY h.created_at DESC, h.id DESC
            """,
            (patient_id,),
        ).fetchall()
    return _rows_to_dicts(rows)


def _parse_bool(value: str) -> int:
    return 1 if value.strip().lower() == "true" else 0


def _parse_patient_id(value: str) -> Optional[int]:
    if not value:
        return None
    return int(float(value))


@observe_operation(layer="db", logger_name=__name__)
def seed_appointments_from_csv(csv_path: Path = DOCTOR_AVAILABILITY_CSV) -> int:
    ensure_database_initialized()

    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))

    appointments = [
        (
            row["date_slot"],
            row["specialization"],
            row["doctor_name"],
            _parse_bool(row["is_available"]),
            _parse_patient_id(row["patient_to_attend"]),
        )
        for row in rows
    ]

    with db_connection() as connection:
        connection.execute("DELETE FROM appointment_history")
        connection.execute("DELETE FROM appointments")
        patient_ids = {
            patient_id
            for _, _, _, is_available, patient_id in appointments
            if not is_available and patient_id is not None
        }
        for patient_id in patient_ids:
            connection.execute(
                """
                INSERT OR IGNORE INTO patients (id, name)
                VALUES (?, ?)
                """,
                (patient_id, f"Imported Patient {patient_id}"),
            )
        connection.executemany(
            """
            INSERT INTO appointments (
                date_slot,
                specialization,
                doctor_name,
                is_available,
                patient_to_attend
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            appointments,
        )

    return len(appointments)


@observe_operation(layer="db", logger_name=__name__)
def count_appointments() -> int:
    ensure_database_initialized()
    with db_connection() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM appointments").fetchone()
    return int(row["total"])


@observe_operation(layer="db", logger_name=__name__)
def check_database_health() -> dict[str, Any]:
    ensure_database_initialized()
    with db_connection() as connection:
        connection.execute("SELECT 1").fetchone()
        patient_count = connection.execute("SELECT COUNT(*) AS total FROM patients").fetchone()
        appointment_count = connection.execute(
            "SELECT COUNT(*) AS total FROM appointments"
        ).fetchone()
    return {
        "status": "ok",
        "database_path": str(DATABASE_PATH),
        "database_exists": DATABASE_PATH.exists(),
        "patients": int(patient_count["total"]),
        "appointments": int(appointment_count["total"]),
    }


if __name__ == "__main__":
    inserted_count = seed_appointments_from_csv()
    print(f"Inserted {inserted_count} appointment records into {DATABASE_PATH}")
    print(f"Total appointments in database: {count_appointments()}")
