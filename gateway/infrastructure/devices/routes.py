"""Device registration, updates, and removal."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from gateway.activity.repository import add_activity_event
from gateway.integrations.simulator import (
    get_simulated_device_state,
    refresh_simulated_devices,
)
from gateway.infrastructure.devices.defaults import DEVICE_DEFAULTS
from gateway.policy.abac import authorize_management_request
from gateway.registry import (
    add_device,
    delete_device,
    generate_next_device_id,
    get_device,
    get_room,
    list_devices,
    update_device,
)
from shared.devices import (
    Device,
    DeviceRegistrationPreview,
    DeviceRegistrationRequest,
    DeviceType,
    DeviceUpdateRequest,
    SecurityState,
)
from shared.policy import Action, ResourceType

router = APIRouter(prefix="/devices", tags=["Devices"])

ActorHeader = Annotated[str | None, Header(alias="X-Actor-ID")]


_DEVICE_TYPE_LABELS = {
    DeviceType.ENVIRONMENTAL_SENSOR: "Environmental Sensor",
    DeviceType.PDU: "Smart PDU",
    DeviceType.HVAC: "HVAC Controller",
    DeviceType.BIOMETRIC_DOOR: "Biometric Door Controller",
    DeviceType.SMOKE_SENSOR: "Smoke Sensor",
}


def _device_type_label(device_type: DeviceType) -> str:
    return _DEVICE_TYPE_LABELS.get(
        device_type, device_type.value.replace("_", " ").title()
    )


def _room_label(room_id: str) -> str:
    room = get_room(room_id)

    if room:
        return f"{room.name} ({room_id})"

    return room_id


def build_registration_preview(device_type: DeviceType) -> DeviceRegistrationPreview:
    device_id = generate_next_device_id(device_type)
    defaults = DEVICE_DEFAULTS[device_type]

    return DeviceRegistrationPreview(
        device_id=device_id,
        name=device_id,
        protocol=defaults["protocol"],
        criticality=defaults["criticality"],
    )


@router.get("")
def api_list_devices():
    return list_devices()


@router.get(
    "/registration-preview/{device_type}", response_model=DeviceRegistrationPreview
)
def api_device_registration_preview(device_type: DeviceType):
    return build_registration_preview(device_type)


@router.get("/{device_id}/operational-state")
async def api_get_device_operational_state(device_id: str):
    device = get_device(device_id)

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    try:
        return await get_simulated_device_state(device_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Simulator state unavailable: {exc}"
        ) from exc


@router.get("/{device_id}")
def api_get_device(device_id: str):
    device = get_device(device_id)

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@router.post("", status_code=201, response_model=Device)
async def create_device(
    request: DeviceRegistrationRequest, x_actor_id: ActorHeader = None
):
    if get_room(request.room_id) is None:
        raise HTTPException(status_code=400, detail="Assigned room does not exist")

    _, personnel = authorize_management_request(
        x_actor_id,
        Action.REGISTER_DEVICE,
        ResourceType.DEVICE,
        "device-registry",
        room_id=request.room_id,
    )

    defaults = DEVICE_DEFAULTS[request.device_type]

    device_id = generate_next_device_id(request.device_type)

    name = request.name.strip() if request.name else device_id

    if not name:
        name = device_id

    device = Device(
        device_id=device_id,
        name=name,
        device_type=request.device_type,
        room_id=request.room_id,
        protocol=defaults["protocol"],
        criticality=defaults["criticality"],
        security_state=SecurityState.NORMAL,
    )

    if not add_device(device):
        raise HTTPException(
            status_code=409,
            detail=("Device ID collision occurred; " "retry registration"),
        )

    device_label = _device_type_label(device.device_type)

    add_activity_event(
        event_type="device_registered",
        source_id=device.device_id,
        room_id=device.room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(
            f"{personnel.name} registered "
            f"{device_label} {device.device_id} "
            f"as '{device.name}' in "
            f"{_room_label(device.room_id)}"
        ),
        metadata={
            "action_text": (f"Register {device_label} " f"{device.device_id}"),
            "cause": (f"Added to " f"{_room_label(device.room_id)}"),
            "target_device_id": (device.device_id),
            "target_device_type": (device.device_type.value),
            "target_name": device.name,
        },
    )

    await refresh_simulated_devices()

    return device


@router.put("/{device_id}", response_model=Device)
async def edit_device(
    device_id: str, request: DeviceUpdateRequest, x_actor_id: ActorHeader = None
):
    device = get_device(device_id)

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    if get_room(request.room_id) is None:
        raise HTTPException(status_code=400, detail="Assigned room does not exist")

    # A room move requires authority over both the current and destination rooms.
    _, personnel = authorize_management_request(
        x_actor_id,
        Action.EDIT_DEVICE,
        ResourceType.DEVICE,
        device_id,
        room_id=device.room_id,
    )
    if request.room_id != device.room_id:
        authorize_management_request(
            x_actor_id,
            Action.EDIT_DEVICE,
            ResourceType.DEVICE,
            device_id,
            room_id=request.room_id,
        )

    name = request.name.strip()

    if not name:
        raise HTTPException(status_code=422, detail="Device name cannot be blank")

    previous_name = device.name
    previous_room_id = device.room_id

    update_device(device_id, name, request.room_id)

    device_label = _device_type_label(device.device_type)

    changes = []

    if previous_name != name:
        changes.append(f"name changed from " f"'{previous_name}' to '{name}'")

    if previous_room_id != request.room_id:
        changes.append(
            f"room changed from "
            f"{_room_label(previous_room_id)} "
            f"to {_room_label(request.room_id)}"
        )

    cause = (
        "; ".join(changes)
        if changes
        else ("Device configuration saved " "with no field changes")
    )

    add_activity_event(
        event_type="device_updated",
        source_id=device_id,
        room_id=request.room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(
            f"{personnel.name} updated " f"{device_label} {device_id}: " f"{cause}"
        ),
        metadata={
            "action_text": (f"Update {device_label} " f"{device_id}"),
            "cause": cause,
            "target_device_id": device_id,
            "target_device_type": (device.device_type.value),
            "previous_name": previous_name,
            "new_name": name,
            "previous_room_id": (previous_room_id),
            "new_room_id": (request.room_id),
        },
    )

    await refresh_simulated_devices()

    return get_device(device_id)


@router.delete("/{device_id}", status_code=204)
async def remove_device(device_id: str, x_actor_id: ActorHeader = None):
    device = get_device(device_id)

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    _, personnel = authorize_management_request(
        x_actor_id,
        Action.DELETE_DEVICE,
        ResourceType.DEVICE,
        device_id,
        room_id=device.room_id,
    )

    if not delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")

    device_label = _device_type_label(device.device_type)

    add_activity_event(
        event_type="device_deleted",
        source_id=device_id,
        room_id=device.room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(
            f"{personnel.name} deleted "
            f"{device_label} {device_id} "
            f"('{device.name}') "
            "from the registry"
        ),
        metadata={
            "action_text": (f"Delete {device_label} " f"{device_id}"),
            "cause": ("Requested through " "Infrastructure management"),
            "target_device_id": device_id,
            "target_device_type": (device.device_type.value),
            "target_name": device.name,
        },
    )

    await refresh_simulated_devices()

    return None
