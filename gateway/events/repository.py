"""Combine separate event sources into the dashboard event view."""

from __future__ import annotations

import json
from datetime import datetime

from gateway.database import get_connection
from gateway.events.messages import humanize as _humanize

TYPE_MANAGEMENT = "Management"
TYPE_CONTROL = "Control"
TYPE_SECURITY = "Security"
TYPE_MITIGATION = "Mitigation"
TYPE_SYSTEM = "System"
TYPE_TELEMETRY = "Telemetry"

_ACTIVITY_TYPES = {
    "device_registered": TYPE_MANAGEMENT,
    "device_updated": TYPE_MANAGEMENT,
    "device_deleted": TYPE_MANAGEMENT,
    "room_registered": TYPE_MANAGEMENT,
    "room_updated": TYPE_MANAGEMENT,
    "room_deleted": TYPE_MANAGEMENT,
    "personnel_created": TYPE_MANAGEMENT,
    "personnel_updated": TYPE_MANAGEMENT,
    "iot_device_policy_created": TYPE_MANAGEMENT,
    "iot_device_policy_updated": TYPE_MANAGEMENT,
    "iot_device_policy_deleted": TYPE_MANAGEMENT,
    "policy_created": TYPE_MANAGEMENT,
    "policy_updated": TYPE_MANAGEMENT,
    "policy_deleted": TYPE_MANAGEMENT,
    "manual_control": TYPE_CONTROL,
    "device_control": TYPE_CONTROL,
    "iot_policy_action": TYPE_CONTROL,
    "door_access_allowed": TYPE_CONTROL,
    "door_access_denied": TYPE_SECURITY,
    "manual_control_denied": TYPE_SECURITY,
    "device_control_denied": TYPE_SECURITY,
    "control_permission_violation": TYPE_SECURITY,
    "management_permission_violation": TYPE_SECURITY,
    "attack_launched": TYPE_SECURITY,
    "security_reset": TYPE_SYSTEM,
    "simulation_environment_changed": TYPE_SYSTEM,
    "iot_policy_no_target": TYPE_SYSTEM,
}


def _activity_action(event_type: str) -> str:
    explicit = {
        "room_registered": "Create Room",
        "room_updated": "Update Room",
        "room_deleted": "Delete Room",
        "device_registered": "Register Device",
        "device_updated": "Update Device",
        "device_deleted": "Delete Device",
        "personnel_created": "Create Personnel",
        "personnel_updated": "Update Personnel",
        "policy_created": "Create ABAC Policy",
        "policy_updated": "Update ABAC Policy",
        "policy_deleted": "Delete ABAC Policy",
        "iot_device_policy_created": "Create IoT Device Policy",
        "iot_device_policy_updated": "Update IoT Device Policy",
        "iot_device_policy_deleted": "Delete IoT Device Policy",
        "manual_control": "Manual Device Control",
        "device_control": "Device-Originated Control",
        "iot_policy_action": "Apply IoT Device Policy",
        "door_access_allowed": "Request Door Access: Allowed",
        "door_access_denied": "Request Door Access: Denied",
        "manual_control_denied": "Manual Device Control: Denied",
        "device_control_denied": "Device-Originated Control: Denied",
        "control_permission_violation": "Manual Device Control: Denied",
        "management_permission_violation": "Management Action: Denied",
        "attack_launched": "Launch Simulated Attack",
        "security_reset": "Reset Device Security State",
        "simulation_environment_changed": "Change Simulation Environment",
        "iot_policy_no_target": "IoT Device Policy Has No Eligible Target",
    }
    return explicit.get(event_type, _humanize(event_type))


def _activity_violation(event_type: str) -> str | None:
    if event_type in {
        "door_access_denied",
        "manual_control_denied",
        "device_control_denied",
    }:
        return "Access Denied"
    if event_type in {
        "control_permission_violation",
        "management_permission_violation",
    }:
        return "ABAC Denied"
    return None


def _state_text(previous_state: str | None, new_state: str | None) -> str | None:
    if not previous_state and not new_state:
        return None
    return f"{_humanize(previous_state)} → {_humanize(new_state)}"


def _activity_metadata(row: dict) -> dict:
    raw = row.get("metadata_json")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _normalise_activity(row: dict) -> dict:
    event_type = row["event_type"]
    category = _ACTIVITY_TYPES.get(event_type, TYPE_SYSTEM)
    metadata = _activity_metadata(row)
    actor = (
        row.get("actor_name") or row.get("resolved_actor_name") or row.get("actor_id")
    )
    if not actor:
        actor = (
            "OT-SOAR Gateway"
            if category in {TYPE_SYSTEM, TYPE_CONTROL}
            else (row.get("source_id") or "OT-SOAR Gateway")
        )

    action = metadata.get("action_text") or _activity_action(event_type)
    cause = metadata.get("cause")
    if not cause and event_type in {
        "door_access_denied",
        "manual_control_denied",
        "device_control_denied",
        "control_permission_violation",
        "management_permission_violation",
        "attack_launched",
        "security_reset",
        "simulation_environment_changed",
    }:
        cause = row["message"]

    public_metadata = {
        "event_type": event_type,
        "actor_clearance": row.get("actor_clearance"),
        **metadata,
    }
    return {
        "event_key": f"activity:{row['event_id']}",
        "timestamp": row["timestamp"],
        "type": category,
        "actor": actor,
        "action": action,
        "cause": cause,
        "violation": _activity_violation(event_type),
        "state": None,
        "message": row["message"],
        "source_id": row.get("source_id"),
        "room_id": row.get("room_id"),
        "origin": "activity",
        "metadata": public_metadata,
    }


def _normalise_security(row: dict) -> dict:
    event_type = row["event_type"]
    is_transition = event_type == "state_transition"
    reason = row.get("reason") or ""
    integrity_transition = is_transition and (
        reason.startswith("Peer-corroboration anomaly:")
        or reason.startswith("Persistent peer-corroboration anomaly:")
    )
    integrity_recovery = is_transition and reason.startswith(
        "Peer-corroboration recovered:"
    )
    action = {
        "state_transition": "Security State Change",
        "integrity_disagreement": "Integrity Check",
        "integrity_recovery_observation": "Observe Telemetry Recovery",
        "monitoring_uncertainty": "Monitoring Uncertainty",
        "policy_violation": "Evaluate Security Policy",
    }.get(event_type, "Evaluate Security Policy")
    return {
        "event_key": f"security:{row['event_id']}",
        "timestamp": row["timestamp"],
        "type": TYPE_SECURITY,
        "actor": row["device_id"],
        "action": action,
        "cause": row.get("reason"),
        "violation": (
            "Telemetry integrity anomaly"
            if event_type == "integrity_disagreement" or integrity_transition
            else (
                "Telemetry integrity recovery"
                if integrity_recovery
                else (
                    "Monitoring uncertainty"
                    if event_type == "monitoring_uncertainty"
                    else (
                        "Telemetry recovery observation"
                        if event_type == "integrity_recovery_observation"
                        else (
                            "Message-rate anomaly"
                            if is_transition
                            and reason.startswith(
                                (
                                    "Sliding-window anomaly:",
                                    "Severe sliding-window anomaly:",
                                )
                            )
                            and (row.get("violation_count") or 0) == 0
                            else (
                                "Policy violation"
                                if event_type == "policy_violation"
                                else (
                                    "Security-state anomaly"
                                    if is_transition
                                    else _humanize(event_type)
                                )
                            )
                        )
                    )
                )
            )
        ),
        "state": _state_text(row.get("previous_state"), row.get("new_state")),
        "message": (
            f"{row['device_id']} changed security state from {_humanize(row.get('previous_state'))} "
            f"to {_humanize(row.get('new_state'))}: {row['reason']}"
            if is_transition
            else f"{row['device_id']}: {row['reason']}"
        ),
        "source_id": row["device_id"],
        "room_id": None,
        "origin": "security",
        "metadata": {
            "event_type": event_type,
            "previous_state": row.get("previous_state"),
            "new_state": row.get("new_state"),
            "message_count": row.get("message_count"),
            "violation_count": row.get("violation_count"),
        },
    }


def _normalise_response(row: dict) -> dict:
    outcome = "Succeeded" if bool(row["success"]) else "Failed"
    return {
        "event_key": f"response:{row['response_id']}",
        "timestamp": row["completed_at"] or row["started_at"],
        "type": TYPE_MITIGATION,
        "actor": "OT-SOAR Gateway",
        "action": _humanize(row["action"]),
        "cause": row["trigger_reason"],
        "violation": "Automatic mitigation",
        "state": None,
        "message": f"Automatic mitigation for {row['device_id']} {outcome.lower()}: {row['outcome']}",
        "source_id": row["device_id"],
        "room_id": row["room_id"],
        "origin": "response",
        "metadata": {
            "strategy": row["strategy"],
            "success": bool(row["success"]),
            "duration_ms": row.get("duration_ms"),
            "device_type": row.get("device_type"),
        },
    }


def _telemetry_message(row: dict) -> str:
    kind = row["telemetry_type"]
    if kind == "environmental":
        values = (
            f"temperature {row['temperature']:.1f} °C, humidity {row['humidity']:.1f}%"
        )
    elif kind == "smoke":
        values = f"smoke level {row['smoke_level']:.1f}"
    else:
        power_state = "on" if row["power_on"] else "off"
        values = f"{row['voltage']:.1f} V, {row['current']:.1f} A, {row['power']:.1f} W, power {power_state}"
    return (
        f"{row['device_id']} published accepted {_humanize(kind)} telemetry: {values}."
    )


def _normalise_telemetry(row: dict) -> dict:
    action = {
        "environmental": "Publish Environmental Telemetry",
        "smoke": "Publish Smoke Telemetry",
        "pdu": "Publish PDU Telemetry",
    }.get(row["telemetry_type"], "Publish Telemetry")
    return {
        "event_key": f"telemetry:{row['telemetry_id']}",
        "timestamp": row["timestamp"],
        "type": TYPE_TELEMETRY,
        "actor": row["device_id"],
        "action": action,
        "cause": None,
        "violation": None,
        "state": None,
        "message": _telemetry_message(row),
        "source_id": row["device_id"],
        "room_id": row["room_id"],
        "origin": "telemetry",
        "metadata": {
            "telemetry_type": row["telemetry_type"],
            "temperature": row.get("temperature"),
            "humidity": row.get("humidity"),
            "smoke_level": row.get("smoke_level"),
            "voltage": row.get("voltage"),
            "current": row.get("current"),
            "power": row.get("power"),
            "power_on": (
                None if row.get("power_on") is None else bool(row.get("power_on"))
            ),
        },
    }


def list_normalized_events(
    types: list[str] | None = None, source_id: str | None = None, limit: int = 100
) -> list[dict]:
    """Return a chronological projection over separate activity, security, response and telemetry stores."""
    requested = set(
        types
        or [TYPE_MANAGEMENT, TYPE_CONTROL, TYPE_SECURITY, TYPE_MITIGATION, TYPE_SYSTEM]
    )
    events: list[dict] = []
    fetch_limit = max(limit * 2, 100)

    with get_connection() as connection:
        if requested & {TYPE_MANAGEMENT, TYPE_CONTROL, TYPE_SYSTEM, TYPE_SECURITY}:
            rows = connection.execute(
                """
                SELECT activity_events.*, personnel.name AS resolved_actor_name
                FROM activity_events
                LEFT JOIN personnel ON personnel.person_id = activity_events.actor_id
                ORDER BY activity_events.event_id DESC
                LIMIT ?
                """,
                (fetch_limit,),
            ).fetchall()
            events.extend(_normalise_activity(dict(row)) for row in rows)

        if TYPE_SECURITY in requested:
            rows = connection.execute(
                "SELECT * FROM security_events ORDER BY event_id DESC LIMIT ?",
                (fetch_limit,),
            ).fetchall()
            events.extend(_normalise_security(dict(row)) for row in rows)

        if TYPE_MITIGATION in requested:
            rows = connection.execute(
                "SELECT * FROM response_events ORDER BY response_id DESC LIMIT ?",
                (fetch_limit,),
            ).fetchall()
            events.extend(_normalise_response(dict(row)) for row in rows)

        if TYPE_TELEMETRY in requested:
            rows = connection.execute(
                "SELECT * FROM telemetry_history ORDER BY telemetry_id DESC LIMIT ?",
                (fetch_limit,),
            ).fetchall()
            events.extend(_normalise_telemetry(dict(row)) for row in rows)

    events = [event for event in events if event["type"] in requested]
    if source_id:
        events = [event for event in events if event.get("source_id") == source_id]
    events.sort(
        key=lambda event: datetime.fromisoformat(event["timestamp"]), reverse=True
    )
    return events[:limit]
