"""Gateway endpoints for the development attack simulator."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gateway.activity.repository import add_activity_event
from gateway.integrations.simulator import get_attack_status, launch_attack
from gateway.registry import get_device
from shared.devices import DeviceType

TELEMETRY_ATTACK_TYPES = {"telemetry_flood", "wrong_room", "slow_poisoning"}
SUPPORTED_ATTACK_TYPES = {*TELEMETRY_ATTACK_TYPES, "unauthorized_control"}
TELEMETRY_DEVICE_TYPES = {
    DeviceType.ENVIRONMENTAL_SENSOR,
    DeviceType.SMOKE_SENSOR,
    DeviceType.PDU,
}


class AttackRequest(BaseModel):
    device_id: str
    attack_type: str
    rate_per_second: int = Field(default=1, ge=1, le=100)
    duration_seconds: int = Field(default=5, ge=1, le=60)


router = APIRouter(prefix="/attack", tags=["Development Attack"])


@router.get("/status")
async def attack_status():
    try:
        return await get_attack_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Attack simulator unavailable"
        ) from exc


@router.post("/launch", status_code=202)
async def start_attack(request: AttackRequest):
    device = get_device(request.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Target device not found")
    if request.attack_type not in SUPPORTED_ATTACK_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported attack type")
    if (
        request.attack_type in TELEMETRY_ATTACK_TYPES
        and device.device_type not in TELEMETRY_DEVICE_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail="Telemetry attacks require an environmental, smoke, or PDU device",
        )
    if (
        request.attack_type == "slow_poisoning"
        and device.device_type != DeviceType.ENVIRONMENTAL_SENSOR
    ):
        raise HTTPException(
            status_code=400, detail="Slow poisoning requires an environmental sensor"
        )

    try:
        result = await launch_attack(request.model_dump())
    except httpx.HTTPStatusError as exc:
        detail = "Attack simulator rejected the request"
        try:
            body = exc.response.json()
            detail = body.get("detail", detail)
        except Exception:
            pass
        raise HTTPException(
            status_code=exc.response.status_code, detail=detail
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Attack simulator unavailable"
        ) from exc

    description = {
        "telemetry_flood": "telemetry flood",
        "wrong_room": "wrong-room telemetry policy violation",
        "slow_poisoning": "time-compressed slow environmental telemetry poisoning",
        "unauthorized_control": "device-originated unauthorized actuator control",
    }[request.attack_type]
    add_activity_event(
        event_type="attack_launched",
        source_id=request.device_id,
        room_id=device.room_id,
        message=f"Development attack {description} launched from {request.device_id}",
    )
    return result
