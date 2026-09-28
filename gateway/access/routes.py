"""Door access requests using an identity supplied by the biometric simulator.

Recognition is outside this prototype. The gateway looks up the person and
checks room access and ABAC policy before sending an unlock command."""

import httpx
from fastapi import APIRouter, HTTPException

from gateway.activity.repository import add_activity_event
from gateway.integrations.simulator import send_door_command
from gateway.policy.abac import authorize_personnel_actuator_request
from gateway.registry import get_device
from shared.commands import DoorAccessRequest, DoorCommand
from shared.devices import DeviceType
from shared.policy import Action

router = APIRouter(prefix="/access", tags=["Access Simulation"])


@router.post("/doors/{device_id}")
async def request_door_access(device_id: str, request: DoorAccessRequest):
    device = get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.device_type != DeviceType.BIOMETRIC_DOOR:
        raise HTTPException(status_code=400, detail="Device is not a biometric door")

    decision, personnel = authorize_personnel_actuator_request(
        request.person_id, device, Action.REQUEST_DOOR_ACCESS
    )

    try:
        result = await send_door_command(device_id, DoorCommand(locked=False))
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Door simulator unavailable"
        ) from exc

    add_activity_event(
        event_type="door_access_allowed",
        source_id=device_id,
        room_id=device.room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(
            f"{device_id} unlocked for {personnel.name} "
            f"(clearance {personnel.clearance})"
        ),
    )
    return {
        "status": "access_granted",
        "person_id": personnel.person_id,
        "person_name": personnel.name,
        "policy_id": decision.policy_id,
        "result": result,
    }
