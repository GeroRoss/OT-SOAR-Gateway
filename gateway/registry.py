"""Room and device records, including gateway-assigned IDs."""

import re
import sqlite3
from gateway.database import get_connection
from shared.devices import Device, DeviceType, SecurityState
from shared.rooms import Room

DEVICE_ID_PREFIXES = {
    DeviceType.ENVIRONMENTAL_SENSOR: "env",
    DeviceType.PDU: "pdu",
    DeviceType.HVAC: "hvac",
    DeviceType.BIOMETRIC_DOOR: "door",
    DeviceType.SMOKE_SENSOR: "smoke",
}


def list_rooms() -> list[Room]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT room_id, name FROM rooms WHERE active = 1 ORDER BY room_id"
        ).fetchall()
    return [Room(room_id=row["room_id"], name=row["name"]) for row in rows]


def get_room(room_id: str) -> Room | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT room_id, name FROM rooms WHERE room_id = ? AND active = 1",
            (room_id,),
        ).fetchone()
    return None if row is None else Room(room_id=row["room_id"], name=row["name"])


def generate_next_room_id() -> str:
    with get_connection() as connection:
        rows = connection.execute("SELECT room_id FROM rooms").fetchall()
    highest = 0
    pattern = re.compile(r"^room-(\d+)$")
    for row in rows:
        match = pattern.match(row["room_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"room-{highest + 1:03d}"


def add_room(room: Room) -> bool:
    try:
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO rooms (room_id, name, active) VALUES (?, ?, 1)",
                (room.room_id, room.name),
            )
    except sqlite3.IntegrityError:
        return False
    return True


def update_room(room_id: str, name: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE rooms SET name = ? WHERE room_id = ? AND active = 1",
            (name, room_id),
        )
    return cursor.rowcount > 0


def get_room_delete_blockers(room_id: str) -> dict[str, int]:
    """Return active references that must be removed before a room can be archived."""
    with get_connection() as connection:
        device_count = connection.execute(
            "SELECT COUNT(*) FROM devices WHERE room_id = ? AND active = 1", (room_id,)
        ).fetchone()[0]
        personnel_count = connection.execute(
            "SELECT COUNT(*) FROM personnel_room_access WHERE room_id = ?", (room_id,)
        ).fetchone()[0]

    return {"devices": int(device_count), "personnel": int(personnel_count)}


def delete_room(room_id: str) -> bool:
    """Soft-delete an unreferenced room while preserving historical identities."""
    blockers = get_room_delete_blockers(room_id)
    if blockers["devices"] or blockers["personnel"]:
        return False

    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE rooms SET active = 0 WHERE room_id = ? AND active = 1", (room_id,)
        )
    return cursor.rowcount > 0


def list_devices() -> list[Device]:
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT device_id, name, device_type, room_id, protocol, criticality, security_state
               FROM devices WHERE active = 1 ORDER BY device_id"""
        ).fetchall()
    return [_row_to_device(row) for row in rows]


def get_device(device_id: str) -> Device | None:
    with get_connection() as connection:
        row = connection.execute(
            """SELECT device_id, name, device_type, room_id, protocol, criticality, security_state
               FROM devices WHERE device_id = ? AND active = 1""",
            (device_id,),
        ).fetchone()
    return None if row is None else _row_to_device(row)


def generate_next_device_id(device_type: DeviceType) -> str:
    prefix = DEVICE_ID_PREFIXES[device_type]
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT device_id FROM devices WHERE device_type = ?", (device_type.value,)
        ).fetchall()
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for row in rows:
        match = pattern.match(row["device_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def add_device(device: Device) -> bool:
    try:
        with get_connection() as connection:
            connection.execute(
                """INSERT INTO devices (device_id, name, device_type, room_id, protocol, criticality, security_state, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    device.device_id,
                    device.name,
                    device.device_type.value,
                    device.room_id,
                    device.protocol.value,
                    device.criticality.value,
                    device.security_state.value,
                ),
            )
    except sqlite3.IntegrityError:
        return False
    return True


def update_device(device_id: str, name: str, room_id: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE devices SET name = ?, room_id = ? WHERE device_id = ?",
            (name, room_id, device_id),
        )
    return cursor.rowcount > 0


def delete_device(device_id: str) -> bool:
    """Soft-delete a device so historical security and telemetry evidence remains intact."""
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE devices SET active = 0 WHERE device_id = ? AND active = 1",
            (device_id,),
        )
    return cursor.rowcount > 0


def update_device_security_state(device_id: str, security_state: SecurityState) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE devices SET security_state = ? WHERE device_id = ?",
            (security_state.value, device_id),
        )
    return cursor.rowcount > 0


def _row_to_device(row) -> Device:
    return Device(
        device_id=row["device_id"],
        name=row["name"],
        device_type=row["device_type"],
        room_id=row["room_id"],
        protocol=row["protocol"],
        criticality=row["criticality"],
        security_state=row["security_state"],
    )


def registry_is_empty() -> bool:
    with get_connection() as connection:
        room_count = connection.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        device_count = connection.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    return room_count == 0 and device_count == 0
