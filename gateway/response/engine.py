"""Choose a quarantine response using device type and simulated room conditions.

Automatic responses call the simulator directly. They are internal gateway
actions and do not pass through personnel-command ABAC checks."""

import time

from gateway.integrations.simulator import (
    get_simulated_device_state_sync,
    get_simulated_environment_sync,
    send_door_command_sync,
    send_hvac_command_sync,
    send_pdu_command_sync,
)
from gateway.registry import get_device
from gateway.response.models import ResponseStrategy
from gateway.response.repository import add_response, utc_now_iso
from shared.commands import DoorCommand, HVACCommand, PDUCommand
from shared.devices import DeviceType, SecurityState

OVERHEAT_TEMPERATURE_C = 35.0
SMOKE_EMERGENCY_LEVEL = 20.0
SAFE_COOLING_LEVEL = 100


def execute_suspicious_response(device_id: str, trigger_reason: str):
    """Record the low-trust containment applied when a device becomes suspicious.

    Suspicious telemetry may still be accepted for monitoring, but seeded
    orchestration policies require NORMAL sources and automated target selection
    excludes suspicious actuators. No physical fail-safe action is taken until
    quarantine, avoiding unnecessary disruption from a temporary anomaly.
    """

    device = get_device(device_id)
    if device is None or device.security_state != SecurityState.SUSPICIOUS:
        return None

    started_at = utc_now_iso()
    started_monotonic = time.monotonic()

    try:
        environment = get_simulated_environment_sync(device.room_id)
    except Exception as exc:
        environment = {"room_id": device.room_id, "environment_lookup_error": str(exc)}

    action = "Reduce trust in suspicious device and exclude it from normal IoT policy orchestration"
    outcome = (
        "Telemetry remains available for monitoring, but NORMAL-state IoT policies "
        "do not use the suspicious device as a trusted source or automated target. "
        "The device may recover automatically after sustained normal behaviour."
    )
    completed_at = utc_now_iso()
    duration_ms = round((time.monotonic() - started_monotonic) * 1000, 3)

    response_id = add_response(
        device_id=device.device_id,
        room_id=device.room_id,
        device_type=device.device_type.value,
        criticality=device.criticality.value,
        trigger_reason=trigger_reason,
        strategy=ResponseStrategy.LOGICAL_CONTAINMENT.value,
        action=action,
        success=True,
        outcome=outcome,
        safety_context=environment,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )

    return {
        "response_id": response_id,
        "device_id": device.device_id,
        "strategy": ResponseStrategy.LOGICAL_CONTAINMENT.value,
        "success": True,
        "outcome": outcome,
        "duration_ms": duration_ms,
    }


def execute_automatic_response(device_id: str, trigger_reason: str):
    """Execute one automatic mitigation after a device enters quarantine."""

    device = get_device(device_id)
    if device is None:
        return None

    started_at = utc_now_iso()
    started_monotonic = time.monotonic()

    try:
        environment = get_simulated_environment_sync(device.room_id)
    except Exception as exc:
        environment = {"room_id": device.room_id, "environment_lookup_error": str(exc)}

    strategy = ResponseStrategy.LOGICAL_CONTAINMENT
    action = "Block normal telemetry/control through quarantine-aware ABAC policies"
    success = True
    outcome = "Logical containment applied; no physical actuator change required."

    try:
        if device.device_type == DeviceType.ENVIRONMENTAL_SENSOR:
            strategy = ResponseStrategy.LOGICAL_CONTAINMENT
            action = "Stop trusting sensor telemetry and require corroboration from other room sources"
            outcome = (
                "Environmental sensor contained logically. The room remains operational while "
                "telemetry from the quarantined sensor is no longer trusted."
            )

        elif device.device_type == DeviceType.SMOKE_SENSOR:
            strategy = ResponseStrategy.MANUAL_SAFETY_VERIFICATION
            action = "Contain sensor logically while preserving the room's independent safety context"
            smoke_level = float(environment.get("smoke_level", 0) or 0)
            if smoke_level >= SMOKE_EMERGENCY_LEVEL:
                outcome = (
                    f"Smoke sensor quarantined while room smoke level is {smoke_level:.1f}. "
                    "Security containment remains active and an immediate physical safety "
                    "verification is required; the incident is not treated as cleared."
                )
            else:
                outcome = (
                    "Smoke sensor quarantined logically. No independent simulated smoke condition "
                    "is currently present, but manual safety verification is required because the "
                    "sensor is safety-critical."
                )

        elif device.device_type == DeviceType.HVAC:
            temperature = float(environment.get("temperature", 0) or 0)
            strategy = ResponseStrategy.FAIL_SAFE_COOLING
            action = f"Command HVAC to {SAFE_COOLING_LEVEL}% cooling, then block normal control"
            send_hvac_command_sync(
                device.device_id, HVACCommand(cooling_level=SAFE_COOLING_LEVEL)
            )
            if temperature >= OVERHEAT_TEMPERATURE_C:
                outcome = (
                    f"HVAC quarantined during overheating ({temperature:.1f} °C). "
                    f"Gateway forced {SAFE_COOLING_LEVEL}% cooling as a safety fallback and "
                    "blocked subsequent normal personnel control."
                )
            else:
                outcome = (
                    f"HVAC quarantined at {temperature:.1f} °C. Gateway placed it in a known "
                    f"safe fallback of {SAFE_COOLING_LEVEL}% cooling before normal control was blocked."
                )

        elif device.device_type == DeviceType.PDU:
            smoke_level = float(environment.get("smoke_level", 0) or 0)
            if smoke_level >= SMOKE_EMERGENCY_LEVEL:
                strategy = ResponseStrategy.EMERGENCY_POWER_ISOLATION
                action = "Turn PDU power off because quarantine coincides with a smoke emergency"
                send_pdu_command_sync(device.device_id, PDUCommand(power_on=False))
                outcome = (
                    f"PDU quarantined with smoke level {smoke_level:.1f}. Power was isolated "
                    "as the safer physical response."
                )
            else:
                strategy = ResponseStrategy.PRESERVE_SAFE_OPERATION
                action = (
                    "Preserve current PDU power state and block further normal control"
                )
                try:
                    state = get_simulated_device_state_sync(device.device_id)
                    current_power = state.get("power_on")
                    if current_power is None:
                        current_power = (state.get("environment") or {}).get(
                            "power_available"
                        )
                except Exception:
                    current_power = environment.get("power_available")
                outcome = (
                    "PDU quarantined without an active smoke emergency. The gateway preserved "
                    f"the current power state ({current_power}) to avoid creating an outage and "
                    "blocked subsequent normal control."
                )

        elif device.device_type == DeviceType.BIOMETRIC_DOOR:
            smoke_level = float(environment.get("smoke_level", 0) or 0)
            if smoke_level >= SMOKE_EMERGENCY_LEVEL:
                strategy = ResponseStrategy.EMERGENCY_EGRESS
                action = "Unlock door for emergency egress, then block normal control"
                send_door_command_sync(device.device_id, DoorCommand(locked=False))
                outcome = (
                    f"Door controller quarantined while smoke level is {smoke_level:.1f}. "
                    "Door was unlocked for emergency egress."
                )
            else:
                strategy = ResponseStrategy.SECURE_DOOR
                action = "Lock door in a secure state, then block normal control"
                send_door_command_sync(device.device_id, DoorCommand(locked=True))
                outcome = (
                    "Door controller quarantined and placed in a locked secure state."
                )

    except Exception as exc:
        success = False
        outcome = f"Mitigation action failed: {exc}"

    completed_at = utc_now_iso()
    duration_ms = round((time.monotonic() - started_monotonic) * 1000, 3)

    response_id = add_response(
        device_id=device.device_id,
        room_id=device.room_id,
        device_type=device.device_type.value,
        criticality=device.criticality.value,
        trigger_reason=trigger_reason,
        strategy=strategy.value,
        action=action,
        success=success,
        outcome=outcome,
        safety_context=environment,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )

    return {
        "response_id": response_id,
        "device_id": device.device_id,
        "strategy": strategy.value,
        "success": success,
        "outcome": outcome,
        "duration_ms": duration_ms,
    }
