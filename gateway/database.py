"""SQLite connections, schema setup, and migrations for existing databases."""

import os
import sqlite3
from contextlib import contextmanager

DATABASE_PATH = os.getenv("GATEWAY_DB_PATH", "/app/data/gateway.db")


@contextmanager
def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _column_exists(connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def initialise_database():
    database_directory = os.path.dirname(DATABASE_PATH)
    if database_directory:
        os.makedirs(database_directory, exist_ok=True)

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )
            """)
        if not _column_exists(connection, "rooms", "active"):
            connection.execute(
                "ALTER TABLE rooms ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
            )

        connection.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                device_type TEXT NOT NULL,
                room_id TEXT NOT NULL,
                protocol TEXT NOT NULL,
                criticality TEXT NOT NULL,
                security_state TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (room_id) REFERENCES rooms(room_id)
            )
            """)
        if not _column_exists(connection, "devices", "active"):
            connection.execute(
                "ALTER TABLE devices ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
            )

        connection.execute("""
            CREATE TABLE IF NOT EXISTS personnel (
                person_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                clearance INTEGER NOT NULL,
                active INTEGER NOT NULL
            )
            """)
        if _column_exists(connection, "personnel", "employment_type"):
            connection.execute("ALTER TABLE personnel DROP COLUMN employment_type")

        connection.execute("""
            CREATE TABLE IF NOT EXISTS personnel_room_access (
                person_id TEXT NOT NULL,
                room_id TEXT NOT NULL,
                PRIMARY KEY (person_id, room_id),
                FOREIGN KEY (person_id) REFERENCES personnel(person_id) ON DELETE CASCADE,
                FOREIGN KEY (room_id) REFERENCES rooms(room_id)
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                policy_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                effect TEXT NOT NULL,
                action TEXT NOT NULL,
                subject_type TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                subject_role TEXT,
                minimum_clearance INTEGER,
                subject_device_type TEXT,
                resource_device_type TEXT,
                require_same_room INTEGER NOT NULL,
                allowed_subject_security_states TEXT,
                allowed_resource_security_states TEXT,
                start_hour INTEGER,
                end_hour INTEGER,
                priority INTEGER NOT NULL,
                enabled INTEGER NOT NULL
            )
            """)
        if not _column_exists(connection, "policies", "minimum_clearance"):
            connection.execute(
                "ALTER TABLE policies ADD COLUMN minimum_clearance INTEGER"
            )

        connection.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                device_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                previous_state TEXT,
                new_state TEXT,
                message_count INTEGER,
                violation_count INTEGER,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS response_events (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                device_id TEXT NOT NULL,
                room_id TEXT NOT NULL,
                device_type TEXT NOT NULL,
                criticality TEXT NOT NULL,
                trigger_reason TEXT NOT NULL,
                strategy TEXT NOT NULL,
                action TEXT NOT NULL,
                success INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                safety_context TEXT NOT NULL,
                duration_ms REAL,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS activity_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source_id TEXT,
                room_id TEXT,
                actor_id TEXT,
                actor_name TEXT,
                actor_clearance INTEGER,
                message TEXT NOT NULL,
                metadata_json TEXT
            )
            """)
        if not _column_exists(connection, "activity_events", "metadata_json"):
            connection.execute(
                "ALTER TABLE activity_events ADD COLUMN metadata_json TEXT"
            )
        connection.execute("""
            CREATE TABLE IF NOT EXISTS abac_policy_seed_state (
                seed_key TEXT PRIMARY KEY,
                version INTEGER NOT NULL
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS iot_device_policies (
                policy_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                policy_type TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                config_json TEXT NOT NULL
            )
            """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_history (
                telemetry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                device_id TEXT NOT NULL,
                room_id TEXT NOT NULL,
                telemetry_type TEXT NOT NULL,
                temperature REAL,
                humidity REAL,
                smoke_level REAL,
                voltage REAL,
                current REAL,
                power REAL,
                power_on INTEGER,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
            """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_history_device_time
            ON telemetry_history(device_id, telemetry_id DESC)
            """)
