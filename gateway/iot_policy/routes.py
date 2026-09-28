"""Automation policy management with personnel authorization checks."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status

from gateway.activity.repository import add_activity_event
from gateway.events.messages import action_text, management_change
from gateway.iot_policy.models import (
    IoTDevicePolicy,
    IoTDevicePolicyCreate,
    IoTDevicePolicyUpdate,
)
from gateway.iot_policy.repository import (
    create_iot_device_policy,
    delete_iot_device_policy,
    get_iot_device_policy,
    list_iot_device_policies,
    update_iot_device_policy,
)
from gateway.iot_policy.validation import (
    IoTPolicyPriorityError,
    validate_iot_policy_priority,
)
from gateway.policy.abac import authorize_management_request
from shared.policy import Action, ResourceType

router = APIRouter(prefix="/iot-policies", tags=["IoT Device Policies"])

ActorHeader = Annotated[str | None, Header(alias="X-Actor-ID")]


_IOT_POLICY_FIELDS = [
    "name",
    "enabled",
    "trigger_device_type",
    "trigger_attribute",
    "operator",
    "threshold",
    "required_source_state",
    "target_device_type",
    "target_scope",
    "action",
    "action_value",
    "fallback_value",
    "priority",
]


_IOT_POLICY_LABELS = {
    "trigger_device_type": "Source device type",
    "trigger_attribute": "Trigger attribute",
    "required_source_state": "Required source state",
    "target_device_type": "Target device type",
    "target_scope": "Target scope",
    "action_value": "Action value",
    "fallback_value": "Fallback value",
}


@router.get("", response_model=list[IoTDevicePolicy])
def list_policies():
    return list_iot_device_policies()


@router.post("", response_model=IoTDevicePolicy, status_code=status.HTTP_201_CREATED)
def create_policy(request: IoTDevicePolicyCreate, x_actor_id: ActorHeader = None):
    _, personnel = authorize_management_request(
        x_actor_id,
        Action.CREATE_IOT_POLICY,
        ResourceType.IOT_POLICY,
        "iot-policy-registry",
    )

    preview = IoTDevicePolicy(policy_id="__new__", **request.model_dump())

    try:
        validate_iot_policy_priority(preview, list_iot_device_policies())
    except IoTPolicyPriorityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    policy = create_iot_device_policy(request)

    action = action_text("Create", "IoT Device Policy", policy.policy_id)

    add_activity_event(
        event_type="iot_device_policy_created",
        source_id=policy.policy_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(f"{personnel.name}: " f"{action}."),
        metadata={
            "action_text": action,
            "cause": ("Policy added to the IoT " "orchestration policy set"),
            "policy_id": policy.policy_id,
            "policy_name": policy.name,
        },
    )

    return policy


@router.put("/{policy_id}", response_model=IoTDevicePolicy)
def update_policy(
    policy_id: str, request: IoTDevicePolicyUpdate, x_actor_id: ActorHeader = None
):
    current = get_iot_device_policy(policy_id)

    if current is None:
        raise HTTPException(status_code=404, detail=("IoT device policy " "not found"))

    _, personnel = authorize_management_request(
        x_actor_id, Action.EDIT_IOT_POLICY, ResourceType.IOT_POLICY, policy_id
    )

    updated = IoTDevicePolicy(policy_id=policy_id, **request.model_dump())

    try:
        validate_iot_policy_priority(updated, list_iot_device_policies())
    except IoTPolicyPriorityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not update_iot_device_policy(updated):
        raise HTTPException(status_code=404, detail=("IoT device policy " "not found"))

    action, cause = management_change(
        entity_type="IoT Device Policy",
        entity_id=policy_id,
        name=None,
        before=current,
        after=updated,
        fields=_IOT_POLICY_FIELDS,
        labels=_IOT_POLICY_LABELS,
    )

    add_activity_event(
        event_type="iot_device_policy_updated",
        source_id=policy_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(f"{personnel.name}: " f"{action}. {cause}."),
        metadata={
            "action_text": action,
            "cause": cause,
            "policy_id": policy_id,
            "policy_name": updated.name,
        },
    )

    return updated


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(policy_id: str, x_actor_id: ActorHeader = None):
    current = get_iot_device_policy(policy_id)

    if current is None:
        raise HTTPException(status_code=404, detail=("IoT device policy " "not found"))

    _, personnel = authorize_management_request(
        x_actor_id, Action.DELETE_IOT_POLICY, ResourceType.IOT_POLICY, policy_id
    )

    if not delete_iot_device_policy(policy_id):
        raise HTTPException(status_code=404, detail=("IoT device policy " "not found"))

    action = action_text("Delete", "IoT Device Policy", policy_id)

    add_activity_event(
        event_type="iot_device_policy_deleted",
        source_id=policy_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(f"{personnel.name}: " f"{action}."),
        metadata={
            "action_text": action,
            "cause": ("Requested through " "IoT Device Policy management"),
            "policy_id": policy_id,
            "policy_name": current.name,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
