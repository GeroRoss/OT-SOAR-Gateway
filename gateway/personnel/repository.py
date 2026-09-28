"""Personnel records, room assignments, and generated IDs."""

import re
import sqlite3

from gateway.database import get_connection
from shared.personnel import Personnel


def list_personnel() -> list[Personnel]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT person_id, name, role, clearance, active FROM personnel ORDER BY person_id"
        ).fetchall()
    return [_row_to_personnel(row) for row in rows]


def get_personnel(person_id: str) -> Personnel | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT person_id, name, role, clearance, active FROM personnel WHERE person_id = ?",
            (person_id,),
        ).fetchone()
    return None if row is None else _row_to_personnel(row)


def generate_next_personnel_id() -> str:
    with get_connection() as connection:
        rows = connection.execute("SELECT person_id FROM personnel").fetchall()
    highest = 0
    pattern = re.compile(r"^personnel-(\d+)$")
    for row in rows:
        match = pattern.match(row["person_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"personnel-{highest + 1:03d}"


def add_personnel(personnel: Personnel) -> bool:
    try:
        with get_connection() as connection:
            connection.execute(
                """INSERT INTO personnel (person_id, name, role, clearance, active)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    personnel.person_id,
                    personnel.name,
                    personnel.role.value,
                    personnel.clearance,
                    int(personnel.active),
                ),
            )
            _insert_room_access(
                connection, personnel.person_id, personnel.authorized_rooms
            )
    except sqlite3.IntegrityError:
        return False
    return True


def update_personnel(person_id: str, personnel: Personnel) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """UPDATE personnel SET name = ?, role = ?, clearance = ?, active = ?
               WHERE person_id = ?""",
            (
                personnel.name,
                personnel.role.value,
                personnel.clearance,
                int(personnel.active),
                person_id,
            ),
        )
        if cursor.rowcount == 0:
            return False
        connection.execute(
            "DELETE FROM personnel_room_access WHERE person_id = ?", (person_id,)
        )
        _insert_room_access(connection, person_id, personnel.authorized_rooms)
    return True


def _insert_room_access(connection, person_id: str, room_ids: list[str]):
    for room_id in room_ids:
        connection.execute(
            "INSERT INTO personnel_room_access (person_id, room_id) VALUES (?, ?)",
            (person_id, room_id),
        )


def _get_authorized_rooms(person_id: str) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT room_id FROM personnel_room_access WHERE person_id = ? ORDER BY room_id",
            (person_id,),
        ).fetchall()
    return [row["room_id"] for row in rows]


def _row_to_personnel(row) -> Personnel:
    return Personnel(
        person_id=row["person_id"],
        name=row["name"],
        role=row["role"],
        clearance=row["clearance"],
        authorized_rooms=_get_authorized_rooms(row["person_id"]),
        active=bool(row["active"]),
    )
