# Run this script to initialize the database and seed it with doctor availability data from the CSV file.

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "clinicgenie.db"
DOCTOR_AVAILABILITY_CSV = DATA_DIR / "doctor_availability.csv"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
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


def initialize_database() -> None:
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_slot TEXT NOT NULL,
                specialization TEXT NOT NULL,
                doctor_name TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                patient_to_attend INTEGER
            )
            """
        )


def _parse_bool(value: str) -> int:
    return 1 if value.strip().lower() == "true" else 0


def _parse_patient_id(value: str) -> Optional[int]:
    if not value:
        return None
    return int(float(value))


def seed_appointments_from_csv(csv_path: Path = DOCTOR_AVAILABILITY_CSV) -> int:
    initialize_database()

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
        connection.execute("DELETE FROM appointments")
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


def count_appointments() -> int:
    initialize_database()
    with db_connection() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM appointments").fetchone()
    return int(row["total"])


if __name__ == "__main__":
    inserted_count = seed_appointments_from_csv()
    print(f"Inserted {inserted_count} appointment records into {DATABASE_PATH}")
    print(f"Total appointments in database: {count_appointments()}")
