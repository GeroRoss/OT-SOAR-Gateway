"""Detector status, event history, and authorized manual device release."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from gateway.activity.repository import add_activity_event
from gateway.policy.abac import authorize_management_request
from gateway.registry import get_device
from gateway.security.detector import detector
from shared.policy import Action, ResourceType

router = APIRouter(prefix="/security", tags=["Security"])
ActorHeader = Annotated[str | None, Header(alias="X-Actor-ID")]


@router.get("/config")
def get_security_configuration():
    return detector.get_configuration()


@router.get("/devices/{device_id}")
def get_device_security_status(device_id: str):
    status = detector.get_status(device_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return status


@router.post("/devices/{device_id}/reset")
def reset_device_security_state(device_id: str, x_actor_id: ActorHeader = None):
    device = get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    _, personnel = authorize_management_request(
        x_actor_id,
        Action.RESET_SECURITY_STATE,
        ResourceType.DEVICE,
        device_id,
        room_id=device.room_id,
    )

    status = detector.reset_device(device_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Device not found")

    add_activity_event(
        event_type="security_reset",
        source_id=device_id,
        room_id=device.room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=f"{personnel.name} manually reset {device_id} to Normal",
        metadata={
            "action_text": f"Reset Security State for {device_id}",
            "cause": "Manual recovery after security review",
        },
    )
    return status
