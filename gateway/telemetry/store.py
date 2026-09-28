"""Cache the latest readings and store accepted telemetry in SQLite."""

from datetime import datetime, timezone
from gateway.database import get_connection
from shared.telemetry import EnvironmentalTelemetry, PDUTelemetry, SmokeTelemetry

environmental_telemetry: dict[str, EnvironmentalTelemetry] = {}
smoke_telemetry: dict[str, SmokeTelemetry] = {}
pdu_telemetry: dict[str, PDUTelemetry] = {}


def clear_latest_telemetry() -> None:
    """Clear in-memory latest-value caches during a demo reset."""
    environmental_telemetry.clear()
    smoke_telemetry.clear()
    pdu_telemetry.clear()


def record_environmental(telemetry: EnvironmentalTelemetry):
    environmental_telemetry[telemetry.device_id] = telemetry
    _insert_history(
        telemetry.device_id,
        telemetry.room_id,
        "environmental",
        temperature=telemetry.temperature,
        humidity=telemetry.humidity,
    )


def record_smoke(telemetry: SmokeTelemetry):
    smoke_telemetry[telemetry.device_id] = telemetry
    _insert_history(
        telemetry.device_id,
        telemetry.room_id,
        "smoke",
        smoke_level=telemetry.smoke_level,
    )


def record_pdu(telemetry: PDUTelemetry):
    pdu_telemetry[telemetry.device_id] = telemetry
    _insert_history(
        telemetry.device_id,
        telemetry.room_id,
        "pdu",
        voltage=telemetry.voltage,
        current=telemetry.current,
        power=telemetry.power,
        power_on=telemetry.power_on,
    )


def get_history(device_id: str, limit: int = 120) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT telemetry_id, timestamp, device_id, room_id, telemetry_type,
                      temperature, humidity, smoke_level, voltage, current, power, power_on
               FROM telemetry_history
               WHERE device_id = ?
               ORDER BY telemetry_id DESC
               LIMIT ?""",
            (device_id, limit),
        ).fetchall()
    result = []
    for row in reversed(rows):
        item = dict(row)
        if item["power_on"] is not None:
            item["power_on"] = bool(item["power_on"])
        result.append(item)
    return result


def _insert_history(
    device_id: str,
    room_id: str,
    telemetry_type: str,
    temperature=None,
    humidity=None,
    smoke_level=None,
    voltage=None,
    current=None,
    power=None,
    power_on=None,
):
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO telemetry_history (
                timestamp, device_id, room_id, telemetry_type,
                temperature, humidity, smoke_level, voltage, current, power, power_on
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                device_id,
                room_id,
                telemetry_type,
                temperature,
                humidity,
                smoke_level,
                voltage,
                current,
                power,
                None if power_on is None else int(power_on),
            ),
        )
