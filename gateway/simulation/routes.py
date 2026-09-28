"""Development controls for the simulated facility environment."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gateway.activity.repository import add_activity_event
from gateway.integrations.simulator import (
    get_simulated_environments,
    update_simulated_environment,
)
from gateway.registry import get_room


class EnvironmentUpdate(BaseModel):
    temperature: float | None = Field(default=None, ge=-20, le=100)
    humidity: float | None = Field(default=None, ge=0, le=100)
    smoke_level: float | None = Field(default=None, ge=0, le=100)
    power_available: bool | None = None


router = APIRouter(prefix="/simulation", tags=["Development Simulation"])


@router.get("/environments")
async def list_environments():
    try:
        return await get_simulated_environments()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Facility simulator unavailable"
        ) from exc


@router.put("/environments/{room_id}")
async def update_environment(room_id: str, update: EnvironmentUpdate):
    if get_room(room_id) is None:
        raise HTTPException(status_code=404, detail="Room not found")
    payload = update.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(
            status_code=400, detail="At least one environment value is required"
        )
    try:
        result = await update_simulated_environment(room_id, payload)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Facility simulator unavailable"
        ) from exc
    add_activity_event(
        event_type="simulation_environment_changed",
        source_id=room_id,
        room_id=room_id,
        message=f"Development simulation changed {room_id}: {payload}",
    )
    return result
