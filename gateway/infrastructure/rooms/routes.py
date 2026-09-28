"""Room registration, updates, and removal."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from gateway.activity.repository import add_activity_event
from gateway.integrations.simulator import refresh_simulated_rooms
from gateway.policy.abac import authorize_management_request
from gateway.registry import (
    add_room,
    delete_room,
    generate_next_room_id,
    get_room,
    get_room_delete_blockers,
    list_rooms,
    update_room,
)
from shared.policy import Action, ResourceType
from shared.rooms import (
    Room,
    RoomRegistrationPreview,
    RoomRegistrationRequest,
    RoomUpdateRequest,
)

router = APIRouter(prefix="/rooms", tags=["Rooms"])
ActorHeader = Annotated[str | None, Header(alias="X-Actor-ID")]


@router.get("")
def api_list_rooms():
    return list_rooms()


@router.get("/registration-preview", response_model=RoomRegistrationPreview)
def room_registration_preview():
    room_id = generate_next_room_id()
    return RoomRegistrationPreview(room_id=room_id, name=room_id)


@router.get("/{room_id}")
def api_get_room(room_id: str):
    room = get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.post("", status_code=201, response_model=Room)
async def create_room(request: RoomRegistrationRequest, x_actor_id: ActorHeader = None):
    _, personnel = authorize_management_request(
        x_actor_id, Action.CREATE_ROOM, ResourceType.ROOM, "room-registry"
    )
    room_id = generate_next_room_id()
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Room name cannot be blank")
    room = Room(room_id=room_id, name=name)
    if not add_room(room):
        raise HTTPException(
            status_code=409, detail="Room ID collision occurred; retry registration"
        )
    add_activity_event(
        event_type="room_registered",
        source_id=room.room_id,
        room_id=room.room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=f"{personnel.name} registered Room {room.room_id} ({room.name})",
        metadata={
            "action_text": f"Create Room {room.room_id}",
            "cause": "Added through Infrastructure management",
        },
    )
    await refresh_simulated_rooms()
    return room


@router.put("/{room_id}", response_model=Room)
def edit_room(room_id: str, request: RoomUpdateRequest, x_actor_id: ActorHeader = None):
    if get_room(room_id) is None:
        raise HTTPException(status_code=404, detail="Room not found")
    _, personnel = authorize_management_request(
        x_actor_id, Action.EDIT_ROOM, ResourceType.ROOM, room_id
    )
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Room name cannot be blank")
    update_room(room_id, name)
    add_activity_event(
        event_type="room_updated",
        source_id=room_id,
        room_id=room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=f"{personnel.name} renamed Room {room_id} to '{name}'",
        metadata={
            "action_text": f"Update Room {room_id}",
            "cause": f"Room name changed to '{name}'",
        },
    )
    return get_room(room_id)


@router.delete("/{room_id}", status_code=204)
async def remove_room(room_id: str, x_actor_id: ActorHeader = None):
    room = get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    _, personnel = authorize_management_request(
        x_actor_id, Action.DELETE_ROOM, ResourceType.ROOM, room_id
    )

    blockers = get_room_delete_blockers(room_id)
    if blockers["devices"] or blockers["personnel"]:
        parts = []
        if blockers["devices"]:
            parts.append(f"{blockers['devices']} active device(s)")
        if blockers["personnel"]:
            parts.append(f"{blockers['personnel']} personnel room assignment(s)")
        raise HTTPException(
            status_code=409,
            detail=(
                f"Room {room_id} cannot be deleted while it is referenced by "
                + " and ".join(parts)
                + ". Move/remove those references first."
            ),
        )

    if not delete_room(room_id):
        raise HTTPException(status_code=409, detail="Room could not be deleted")

    add_activity_event(
        event_type="room_deleted",
        source_id=room_id,
        room_id=room_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=f"{personnel.name} deleted Room {room_id} ({room.name})",
        metadata={
            "action_text": f"Delete Room {room_id}",
            "cause": "Removed through Infrastructure management",
        },
    )
    await refresh_simulated_rooms()
    return None
