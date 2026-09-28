"""Build ABAC attributes from registry records and authorize requests."""

from datetime import datetime

from fastapi import HTTPException

from gateway.activity.repository import add_activity_event
from gateway.personnel.repository import get_personnel
from gateway.policy.engine import evaluate_policy
from gateway.registry import get_device
from gateway.security.detector import detector
from shared.devices import Device, DeviceType
from shared.policy import (
    Action,
    PolicyRequest,
    RequestContext,
    ResourceAttributes,
    ResourceType,
    SubjectAttributes,
    SubjectType,
)

_DEVICE_TYPE_LABELS = {
    DeviceType.ENVIRONMENTAL_SENSOR: "Environmental Sensor",
    DeviceType.PDU: "Smart PDU",
    DeviceType.HVAC: "HVAC Controller",
    DeviceType.BIOMETRIC_DOOR: "Biometric Door Controller",
    DeviceType.SMOKE_SENSOR: "Smoke Sensor",
}

_ACTION_LABELS = {
    Action.CONTROL_HVAC: "Control HVAC",
    Action.CONTROL_PDU: "Control PDU",
    Action.CONTROL_DOOR: "Control Door",
    Action.CREATE_ROOM: "Create Room",
    Action.EDIT_ROOM: "Update Room",
    Action.DELETE_ROOM: "Delete Room",
    Action.REGISTER_DEVICE: "Register Device",
    Action.EDIT_DEVICE: "Update Device",
    Action.DELETE_DEVICE: "Delete Device",
    Action.CREATE_PERSONNEL: "Create Personnel",
    Action.EDIT_PERSONNEL: "Update Personnel",
    Action.CREATE_IOT_POLICY: "Create IoT Device Policy",
    Action.EDIT_IOT_POLICY: "Update IoT Device Policy",
    Action.DELETE_IOT_POLICY: "Delete IoT Device Policy",
    Action.CREATE_ABAC_POLICY: "Create ABAC Policy",
    Action.EDIT_ABAC_POLICY: "Update ABAC Policy",
    Action.DELETE_ABAC_POLICY: "Delete ABAC Policy",
}


def current_context() -> RequestContext:
    return RequestContext(hour=datetime.now().hour)


def build_device_subject(device: Device) -> SubjectAttributes:
    return SubjectAttributes(
        subject_id=device.device_id,
        subject_type=SubjectType.DEVICE,
        device_type=device.device_type,
        room_id=device.room_id,
        security_state=device.security_state,
    )


def build_device_resource(device: Device) -> ResourceAttributes:
    return ResourceAttributes(
        resource_id=device.device_id,
        resource_type=ResourceType.DEVICE,
        room_id=device.room_id,
        device_type=device.device_type,
        security_state=device.security_state,
    )


def build_personnel_subject(personnel, room_id: str | None):
    return SubjectAttributes(
        subject_id=personnel.person_id,
        subject_type=SubjectType.PERSONNEL,
        role=personnel.role.value,
        clearance=personnel.clearance,
        room_id=room_id,
    )


def _action_label(action: Action) -> str:
    return _ACTION_LABELS.get(action, action.value.replace("_", " ").title())


def _resource_label(resource_id: str, resource_type: ResourceType) -> str:
    """Return a human-readable audit target without changing ABAC data."""

    if resource_type == ResourceType.DEVICE:
        device = get_device(resource_id)

        if device is not None:
            device_type = _DEVICE_TYPE_LABELS.get(
                device.device_type, device.device_type.value.replace("_", " ").title()
            )

            return f"{device_type} {device.device_id}"

        if resource_id == "device-registry":
            return "Device Registry"

    if resource_type == ResourceType.ROOM:
        return (
            "Room Registry" if resource_id == "room-registry" else f"Room {resource_id}"
        )

    if resource_type == ResourceType.PERSONNEL:
        return f"Personnel {resource_id}"

    if resource_type == ResourceType.IOT_POLICY:
        return f"IoT Device Policy {resource_id}"

    if resource_type == ResourceType.ABAC_POLICY:
        return f"ABAC Policy {resource_id}"

    return resource_id


def _denied_action_text(
    action: Action, resource_id: str, resource_type: ResourceType
) -> str:
    action_label = _action_label(action)
    target = _resource_label(resource_id, resource_type)

    if resource_id in {"device-registry", "room-registry"}:
        return action_label

    return f"{action_label} {target}"


def _deny_personnel_event(
    personnel,
    event_type: str,
    action: Action,
    resource_id: str,
    resource_type: ResourceType,
    reason: str,
):
    action_text = _denied_action_text(action, resource_id, resource_type)
    action_label = _action_label(action)
    target_label = _resource_label(resource_id, resource_type)
    denied_action_text = (
        f"{action_label}: Denied"
        if resource_id in {"device-registry", "room-registry"}
        else f"{action_label}: Denied — {target_label}"
    )

    add_activity_event(
        event_type=event_type,
        source_id=resource_id,
        actor_id=personnel.person_id,
        actor_name=personnel.name,
        actor_clearance=personnel.clearance,
        message=(
            f"{personnel.name} was denied permission to "
            f"{action_text.lower()}. {reason}"
        ),
        metadata={
            "action_text": denied_action_text,
            "cause": reason,
            "requested_action": action.value,
            "resource_type": resource_type.value,
            "resource_id": resource_id,
        },
    )


def authorize_device_telemetry(device_id: str, reported_room_id: str, action: Action):
    device = get_device(device_id)

    if device is None:
        raise HTTPException(status_code=403, detail="Unknown device")

    request = PolicyRequest(
        subject=build_device_subject(device),
        action=action,
        resource=ResourceAttributes(
            resource_id=f"telemetry:{device_id}",
            resource_type=ResourceType.TELEMETRY,
            room_id=reported_room_id,
        ),
        context=current_context(),
    )

    decision = evaluate_policy(request)

    if not decision.allowed:
        detector.record_policy_violation(
            device_id=device_id,
            reason=(
                f"ABAC denied {action.value} "
                f"for telemetry:{device_id} "
                f"in room context {reported_room_id}"
            ),
        )

        raise HTTPException(
            status_code=403,
            detail={
                "message": "ABAC policy denied telemetry",
                "decision": decision.model_dump(),
            },
        )

    return decision


def authorize_personnel_actuator_request(
    person_id: str, target_device: Device, action: Action
):
    personnel = get_personnel(person_id)

    if personnel is None:
        raise HTTPException(status_code=403, detail="Unknown personnel identity")

    if not personnel.active:
        raise HTTPException(status_code=403, detail="Personnel record is inactive")

    resource_label = _resource_label(target_device.device_id, ResourceType.DEVICE)

    action_text = _denied_action_text(
        action, target_device.device_id, ResourceType.DEVICE
    )

    if target_device.room_id not in personnel.authorized_rooms:
        reason = f"Personnel is not authorized for room " f"{target_device.room_id}."

        _deny_personnel_event(
            personnel,
            "control_permission_violation",
            action,
            target_device.device_id,
            ResourceType.DEVICE,
            reason,
        )

        raise HTTPException(
            status_code=403,
            detail=(
                f"{personnel.name} is not authorized to "
                f"{action_text.lower()}. "
                f"The target {resource_label} is in "
                f"{target_device.room_id}, which is outside "
                "this account's authorized rooms."
            ),
        )

    request = PolicyRequest(
        subject=build_personnel_subject(personnel, room_id=target_device.room_id),
        action=action,
        resource=build_device_resource(target_device),
        context=current_context(),
    )

    decision = evaluate_policy(request)

    if not decision.allowed:
        _deny_personnel_event(
            personnel,
            "control_permission_violation",
            action,
            target_device.device_id,
            ResourceType.DEVICE,
            decision.reason,
        )

        raise HTTPException(
            status_code=403,
            detail=(
                f"{personnel.name} is not authorized to "
                f"{action_text.lower()} under the current "
                "ABAC policy."
            ),
        )

    return decision, personnel


def authorize_management_request(
    person_id: str | None,
    action: Action,
    resource_type: ResourceType,
    resource_id: str,
    room_id: str | None = None,
):
    """Authorize a management action using trusted personnel attributes."""

    if not person_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "A current personnel account is required " "for this management action"
            ),
        )

    personnel = get_personnel(person_id)

    if personnel is None:
        raise HTTPException(status_code=403, detail="Unknown personnel identity")

    if not personnel.active:
        raise HTTPException(status_code=403, detail="Personnel record is inactive")

    action_text = _denied_action_text(action, resource_id, resource_type)

    if room_id is not None and room_id not in personnel.authorized_rooms:
        reason = f"Personnel is not authorized for room " f"{room_id}."

        _deny_personnel_event(
            personnel,
            "management_permission_violation",
            action,
            resource_id,
            resource_type,
            reason,
        )

        raise HTTPException(
            status_code=403,
            detail=(
                f"{personnel.name} is not authorized to "
                f"{action_text.lower()}. "
                f"Room {room_id} is outside this account's "
                "authorized rooms."
            ),
        )

    request = PolicyRequest(
        subject=build_personnel_subject(personnel, room_id=room_id),
        action=action,
        resource=ResourceAttributes(
            resource_id=resource_id, resource_type=resource_type, room_id=room_id
        ),
        context=current_context(),
    )

    decision = evaluate_policy(request)

    if not decision.allowed:
        _deny_personnel_event(
            personnel,
            "management_permission_violation",
            action,
            resource_id,
            resource_type,
            decision.reason,
        )

        raise HTTPException(
            status_code=403,
            detail=(
                f"{personnel.name} is not authorized to "
                f"{action_text.lower()} under the current "
                "ABAC policy."
            ),
        )

    return decision, personnel


def authorize_device_actuator_request(
    source_device_id: str, target_device: Device, action: Action
):
    """Authorize a registered device attempting actuator control."""

    source_device = get_device(source_device_id)

    if source_device is None:
        raise HTTPException(status_code=403, detail="Unknown source device")

    request = PolicyRequest(
        subject=build_device_subject(source_device),
        action=action,
        resource=build_device_resource(target_device),
        context=current_context(),
    )

    decision = evaluate_policy(request)

    if not decision.allowed:
        detector.record_policy_violation(
            device_id=source_device.device_id,
            reason=(
                f"ABAC denied device-originated action "
                f"{action.value} from "
                f"{source_device.device_id} to "
                f"{target_device.device_id}"
            ),
        )

        raise HTTPException(
            status_code=403,
            detail={
                "message": ("ABAC policy denied " "device-originated actuator request"),
                "decision": decision.model_dump(),
            },
        )

    return decision, source_device
