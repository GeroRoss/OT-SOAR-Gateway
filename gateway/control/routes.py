"""Personnel and device requests to control simulated actuators.

Personnel actions record the operator, target, and override reason.
Device-originated requests also support the lateral-movement evaluation."""

import httpx
from fastapi import APIRouter, HTTPException

from gateway.activity.repository import add_activity_event
from gateway.integrations.simulator import (
    send_door_command,
    send_hvac_command,
    send_pdu_command,
)
from gateway.policy.abac import (
    authorize_device_actuator_request,
    authorize_personnel_actuator_request,
)
from gateway.registry import get_device
from shared.commands import (
    DeviceDoorControlRequest,
    DeviceHVACControlRequest,
    DevicePDUControlRequest,
    DoorControlRequest,
    HVACControlRequest,
    PDUControlRequest,
)
from shared.devices import DeviceType
from shared.policy import Action

router = APIRouter(prefix="/devices", tags=["Device Control"])


_DEVICE_TYPE_LABELS = {
    DeviceType.HVAC: "HVAC Controller",
    DeviceType.PDU: "Smart PDU",
    DeviceType.BIOMETRIC_DOOR: ("Biometric Door Controller"),
}


def _require_device(device_id: str, expected_type: DeviceType):
    device = get_device(device_id)

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.device_type != expected_type:
        raise HTTPException(
            status_code=400,
            detail=(f"Device is not a " f"{expected_type.value} actuator"),
        )

    return device


def _target_label(device) -> str:
    device_type = _DEVICE_TYPE_LABELS.get(
        device.device_type, device.device_type.value.replace("_", " ").title()
    )

    return f"{device_type} " f"{device.device_id}"


def _log_manual_control(
    personnel, device, action_text: str, outcome_text: str, metadata: dict
):
    add_activity_event(
        event_type="manual_control",
        source_id=device.device_id,
        room_id=device.room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(f"{personnel.name} " f"{outcome_text}"),
        metadata={
            "action_text": action_text,
            "cause": "Manual override",
            "target_device_id": (device.device_id),
            "target_device_type": (device.device_type.value),
            "target_name": device.name,
            **metadata,
        },
    )


@router.post("/{device_id}/commands/hvac")
async def command_hvac(device_id: str, request: HVACControlRequest):
    device = _require_device(device_id, DeviceType.HVAC)

    decision, personnel = authorize_personnel_actuator_request(
        request.person_id, device, Action.CONTROL_HVAC
    )

    try:
        result = await send_hvac_command(device_id, request.command)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail=("HVAC simulator unavailable")
        ) from exc

    level = request.command.cooling_level

    target = _target_label(device)

    _log_manual_control(
        personnel,
        device,
        action_text=(f"Set {target} " f"Cooling to {level}%"),
        outcome_text=(f"set {target} " f"cooling to {level}%"),
        metadata={"control": "cooling_level", "target_value": level},
    )

    return {"status": "executed", "policy_id": decision.policy_id, "result": result}


@router.post("/{device_id}/commands/pdu")
async def command_pdu(device_id: str, request: PDUControlRequest):
    device = _require_device(device_id, DeviceType.PDU)

    decision, personnel = authorize_personnel_actuator_request(
        request.person_id, device, Action.CONTROL_PDU
    )

    try:
        result = await send_pdu_command(device_id, request.command)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail=("PDU simulator unavailable")
        ) from exc

    target = _target_label(device)

    verb = "Turn On" if request.command.power_on else "Turn Off"

    outcome = "turned on" if request.command.power_on else "turned off"

    _log_manual_control(
        personnel,
        device,
        action_text=(f"{verb} {target}"),
        outcome_text=(f"{outcome} {target}"),
        metadata={"control": "power_on", "target_value": (request.command.power_on)},
    )

    return {"status": "executed", "policy_id": decision.policy_id, "result": result}


@router.post("/{device_id}/commands/door")
async def command_door(device_id: str, request: DoorControlRequest):
    device = _require_device(device_id, DeviceType.BIOMETRIC_DOOR)

    decision, personnel = authorize_personnel_actuator_request(
        request.person_id, device, Action.CONTROL_DOOR
    )

    try:
        result = await send_door_command(device_id, request.command)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail=("Door simulator unavailable")
        ) from exc

    target = _target_label(device)

    verb = "Lock" if request.command.locked else "Unlock"

    outcome = "locked" if request.command.locked else "unlocked"

    _log_manual_control(
        personnel,
        device,
        action_text=(f"{verb} {target}"),
        outcome_text=(f"{outcome} {target}"),
        metadata={"control": "locked", "target_value": (request.command.locked)},
    )

    return {"status": "executed", "policy_id": decision.policy_id, "result": result}


@router.post("/{device_id}/commands/device/hvac")
async def device_command_hvac(device_id: str, request: DeviceHVACControlRequest):
    target = _require_device(device_id, DeviceType.HVAC)

    decision, source = authorize_device_actuator_request(
        request.source_device_id, target, Action.CONTROL_HVAC
    )

    try:
        result = await send_hvac_command(device_id, request.command)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail=("HVAC simulator unavailable")
        ) from exc

    level = request.command.cooling_level

    add_activity_event(
        event_type="device_control",
        source_id=source.device_id,
        room_id=source.room_id,
        message=(
            f"{source.device_id} set "
            f"{_target_label(target)} "
            f"cooling to {level}% "
            "through ABAC"
        ),
        metadata={
            "action_text": (f"Set {_target_label(target)} " f"Cooling to {level}%"),
            "cause": ("Device-originated request " f"from {source.device_id}"),
            "target_device_id": (target.device_id),
            "target_value": level,
        },
    )

    return {"status": "executed", "policy_id": decision.policy_id, "result": result}


@router.post("/{device_id}/commands/device/pdu")
async def device_command_pdu(device_id: str, request: DevicePDUControlRequest):
    target = _require_device(device_id, DeviceType.PDU)

    decision, source = authorize_device_actuator_request(
        request.source_device_id, target, Action.CONTROL_PDU
    )

    try:
        result = await send_pdu_command(device_id, request.command)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail=("PDU simulator unavailable")
        ) from exc

    verb = "Turn On" if request.command.power_on else "Turn Off"

    add_activity_event(
        event_type="device_control",
        source_id=source.device_id,
        room_id=source.room_id,
        message=(
            f"{source.device_id} controlled " f"{_target_label(target)} " "through ABAC"
        ),
        metadata={
            "action_text": (f"{verb} " f"{_target_label(target)}"),
            "cause": ("Device-originated request " f"from {source.device_id}"),
            "target_device_id": (target.device_id),
            "target_value": (request.command.power_on),
        },
    )

    return {"status": "executed", "policy_id": decision.policy_id, "result": result}


@router.post("/{device_id}/commands/device/door")
async def device_command_door(device_id: str, request: DeviceDoorControlRequest):
    target = _require_device(device_id, DeviceType.BIOMETRIC_DOOR)

    decision, source = authorize_device_actuator_request(
        request.source_device_id, target, Action.CONTROL_DOOR
    )

    try:
        result = await send_door_command(device_id, request.command)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail=("Door simulator unavailable")
        ) from exc

    verb = "Lock" if request.command.locked else "Unlock"

    add_activity_event(
        event_type="device_control",
        source_id=source.device_id,
        room_id=source.room_id,
        message=(
            f"{source.device_id} controlled " f"{_target_label(target)} " "through ABAC"
        ),
        metadata={
            "action_text": (f"{verb} " f"{_target_label(target)}"),
            "cause": ("Device-originated request " f"from {source.device_id}"),
            "target_device_id": (target.device_id),
            "target_value": (request.command.locked),
        },
    )

    return {"status": "executed", "policy_id": decision.policy_id, "result": result}
