"""Personnel lookup and authorized account management."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from gateway.activity.repository import add_activity_event
from gateway.personnel.repository import (
    add_personnel,
    generate_next_personnel_id,
    get_personnel,
    list_personnel,
    update_personnel,
)
from gateway.policy.abac import authorize_management_request
from gateway.registry import get_room
from shared.personnel import (
    Personnel,
    PersonnelRegistrationPreview,
    PersonnelRegistrationRequest,
    PersonnelRole,
    PersonnelUpdateRequest,
)
from shared.policy import Action, ResourceType

router = APIRouter(prefix="/personnel", tags=["Personnel"])
ActorHeader = Annotated[str | None, Header(alias="X-Actor-ID")]


@router.get("")
def api_list_personnel():
    return list_personnel()


@router.get("/registration-preview", response_model=PersonnelRegistrationPreview)
def registration_preview():
    return PersonnelRegistrationPreview(person_id=generate_next_personnel_id())


@router.get("/{person_id}")
def api_get_personnel(person_id: str):
    personnel = get_personnel(person_id)
    if personnel is None:
        raise HTTPException(status_code=404, detail="Personnel record not found")
    return personnel


@router.post("", status_code=201, response_model=Personnel)
def create_personnel(
    request: PersonnelRegistrationRequest, x_actor_id: ActorHeader = None
):
    _, actor = authorize_management_request(
        x_actor_id,
        Action.CREATE_PERSONNEL,
        ResourceType.PERSONNEL,
        "personnel-registry",
    )
    _validate_authorized_rooms(request.authorized_rooms)
    _validate_assignment_authority(actor, request.role, request.clearance)

    person_id = generate_next_personnel_id()
    personnel = Personnel(
        person_id=person_id,
        name=request.name.strip(),
        role=request.role,
        clearance=request.clearance,
        authorized_rooms=request.authorized_rooms,
        active=request.active,
    )
    if not personnel.name:
        raise HTTPException(status_code=422, detail="Personnel name cannot be blank")
    if not add_personnel(personnel):
        raise HTTPException(
            status_code=409,
            detail="Personnel ID collision occurred; retry registration",
        )

    add_activity_event(
        event_type="personnel_created",
        source_id=personnel.person_id,
        actor_id=actor.person_id,
        actor_name=actor.name,
        actor_clearance=actor.clearance,
        message=f"{actor.name} created personnel record for {personnel.name} (clearance {personnel.clearance})",
        metadata={
            "action_text": f"Create Personnel {personnel.person_id}",
            "cause": "Added through Personnel management",
        },
    )
    return personnel


@router.put("/{person_id}", response_model=Personnel)
def replace_personnel(
    person_id: str, request: PersonnelUpdateRequest, x_actor_id: ActorHeader = None
):
    existing = get_personnel(person_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Personnel record not found")

    _, actor = authorize_management_request(
        x_actor_id, Action.EDIT_PERSONNEL, ResourceType.PERSONNEL, person_id
    )
    _validate_authorized_rooms(request.authorized_rooms)
    _validate_assignment_authority(actor, request.role, request.clearance)
    _validate_self_edit(actor, existing, request)

    personnel = Personnel(
        person_id=person_id,
        name=request.name.strip(),
        role=request.role,
        clearance=request.clearance,
        authorized_rooms=request.authorized_rooms,
        active=request.active,
    )
    if not personnel.name:
        raise HTTPException(status_code=422, detail="Personnel name cannot be blank")

    update_personnel(person_id, personnel)
    add_activity_event(
        event_type="personnel_updated",
        source_id=person_id,
        actor_id=actor.person_id,
        actor_name=actor.name,
        actor_clearance=actor.clearance,
        message=f"{actor.name} updated personnel record for {personnel.name} (clearance {personnel.clearance}, active={personnel.active})",
        metadata={
            "action_text": f"Update Personnel {person_id}",
            "cause": "Personnel attributes updated",
        },
    )
    return get_personnel(person_id)


def _validate_authorized_rooms(room_ids: list[str]):
    if len(room_ids) != len(set(room_ids)):
        raise HTTPException(
            status_code=400, detail="authorized_rooms contains duplicate room IDs"
        )
    for room_id in room_ids:
        if get_room(room_id) is None:
            raise HTTPException(
                status_code=400, detail=f"Authorized room does not exist: {room_id}"
            )


def _validate_assignment_authority(
    actor: Personnel, role: PersonnelRole, clearance: int
) -> None:
    """Prevent a personnel editor from granting authority above their own."""

    if clearance > actor.clearance:
        raise HTTPException(
            status_code=403,
            detail=f"{actor.name} cannot assign clearance {clearance} above their own clearance {actor.clearance}.",
        )

    if (
        role == PersonnelRole.OT_ADMINISTRATOR
        and actor.role != PersonnelRole.OT_ADMINISTRATOR
    ):
        raise HTTPException(
            status_code=403,
            detail="Only an OT Administrator can assign the OT Administrator role.",
        )


def _validate_self_edit(
    actor: Personnel, existing: Personnel, request: PersonnelUpdateRequest
) -> None:
    """Allow harmless self-edits but prevent self-escalation or self-reactivation changes."""

    if actor.person_id != existing.person_id:
        return

    if (
        request.role != existing.role
        or request.clearance != existing.clearance
        or request.active != existing.active
    ):
        raise HTTPException(
            status_code=403,
            detail="Personnel cannot change their own role, clearance, or active status.",
        )
