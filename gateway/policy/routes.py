"""ABAC policy management with personnel authorization checks."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status

from gateway.activity.repository import add_activity_event
from gateway.events.messages import action_text, management_change
from gateway.policy.abac import authorize_management_request
from gateway.policy.repository import (
    create_policy as create_policy_record,
    delete_policy,
    get_policy,
    list_policies,
    update_policy,
)
from shared.policy import Action, Policy, PolicyCreate, ResourceType

router = APIRouter(prefix="/policies", tags=["Policies"])

ActorHeader = Annotated[str | None, Header(alias="X-Actor-ID")]


_POLICY_FIELDS = [
    "name",
    "enabled",
    "effect",
    "action",
    "subject_type",
    "subject_roles",
    "minimum_clearance",
    "subject_device_type",
    "resource_type",
    "resource_device_type",
    "require_same_room",
    "allowed_subject_security_states",
    "allowed_resource_security_states",
    "start_hour",
    "end_hour",
    "priority",
]


_POLICY_LABELS = {
    "minimum_clearance": "Minimum clearance",
    "subject_roles": "Eligible roles",
    "subject_device_type": "Subject device type",
    "resource_device_type": "Resource device type",
    "require_same_room": "Same-room requirement",
    "allowed_subject_security_states": "Allowed subject states",
    "allowed_resource_security_states": "Allowed resource states",
    "start_hour": "Start hour",
    "end_hour": "End hour",
}


def _validate_priority(priority: int):
    if priority < 1 or priority > 9:
        raise HTTPException(
            status_code=422, detail=("ABAC policy priority must " "be between 1 and 9")
        )


def _list_text(value) -> str:
    if value is None:
        return "Any"

    if not isinstance(value, list):
        return str(value)

    if not value:
        return "Any"

    parts = []

    for item in value:
        raw = getattr(item, "value", item)

        text = str(raw).replace("_", " ")

        parts.append(text.title())

    return ", ".join(parts)


_POLICY_FORMATTERS = {
    "subject_roles": _list_text,
    "allowed_subject_security_states": _list_text,
    "allowed_resource_security_states": _list_text,
}


@router.get("")
def api_list_policies():
    return list_policies()


@router.get("/{policy_id}")
def api_get_policy(policy_id: str):
    policy = get_policy(policy_id)

    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    return policy


@router.post("", status_code=201, response_model=Policy)
def create_policy(policy: PolicyCreate, x_actor_id: ActorHeader = None):
    _validate_priority(policy.priority)

    _, personnel = authorize_management_request(
        x_actor_id,
        Action.CREATE_ABAC_POLICY,
        ResourceType.ABAC_POLICY,
        "new-abac-policy",
    )

    try:
        created = create_policy_record(policy)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    action = action_text("Create", "ABAC Policy", created.policy_id)

    add_activity_event(
        event_type="policy_created",
        source_id=created.policy_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(
            f"{personnel.name} created " f"{created.policy_id}: " f"{created.name}"
        ),
        metadata={
            "action_text": action,
            "cause": ("Policy added to the " "ABAC policy set"),
            "policy_id": created.policy_id,
            "policy_name": created.name,
        },
    )

    return created


@router.put("/{policy_id}", response_model=Policy)
def replace_policy(policy_id: str, policy: Policy, x_actor_id: ActorHeader = None):
    if policy.policy_id != policy_id:
        raise HTTPException(
            status_code=400,
            detail=("policy_id in request body " "must match URL policy_id"),
        )

    current = get_policy(policy_id)

    if current is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    _validate_priority(policy.priority)

    _, personnel = authorize_management_request(
        x_actor_id, Action.EDIT_ABAC_POLICY, ResourceType.ABAC_POLICY, policy_id
    )

    if not update_policy(policy_id, policy):
        raise HTTPException(status_code=404, detail="Policy not found")

    action, cause = management_change(
        entity_type="ABAC Policy",
        entity_id=policy_id,
        name=None,
        before=current,
        after=policy,
        fields=_POLICY_FIELDS,
        labels=_POLICY_LABELS,
        formatters=_POLICY_FORMATTERS,
    )

    add_activity_event(
        event_type="policy_updated",
        source_id=policy_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(f"{personnel.name}: " f"{action}. {cause}."),
        metadata={
            "action_text": action,
            "cause": cause,
            "policy_id": policy_id,
            "policy_name": policy.name,
        },
    )

    return get_policy(policy_id)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_policy(policy_id: str, x_actor_id: ActorHeader = None):
    existing = get_policy(policy_id)

    if existing is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    _, personnel = authorize_management_request(
        x_actor_id, Action.DELETE_ABAC_POLICY, ResourceType.ABAC_POLICY, policy_id
    )

    if not delete_policy(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")

    action = action_text("Delete", "ABAC Policy", policy_id)

    add_activity_event(
        event_type="policy_deleted",
        source_id=policy_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(f"{personnel.name} deleted " f"{policy_id}: " f"{existing.name}"),
        metadata={
            "action_text": action,
            "cause": ("Requested through " "ABAC policy management"),
            "policy_id": policy_id,
            "policy_name": existing.name,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
