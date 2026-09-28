"""Check automation priorities and target scope before saving a policy."""

from gateway.iot_policy.models import IoTAction, IoTDevicePolicy, IoTTargetScope


class IoTPolicyPriorityError(ValueError):
    """Raised when a discrete actuator policy has an ambiguous priority."""


def validate_iot_policy_priority(
    candidate: IoTDevicePolicy, existing: list[IoTDevicePolicy]
) -> None:
    """Enforce deterministic priorities for PDU and door desired-state rules.

    HVAC rules intentionally do not use numerical priority: their cooling
    demands are aggregated by taking the maximum requested output.  PDU and
    biometric-door actions are discrete and therefore require unique priority
    values for the same target action.  A whole-facility rule must also outrank
    every same-room rule for that target action because their target sets can
    overlap at runtime.
    """

    if candidate.action == IoTAction.SET_COOLING:
        return

    comparable = [
        policy
        for policy in existing
        if policy.policy_id != candidate.policy_id
        and policy.target_device_type == candidate.target_device_type
        and policy.action == candidate.action
    ]

    duplicate = next(
        (policy for policy in comparable if policy.priority == candidate.priority), None
    )
    if duplicate is not None:
        raise IoTPolicyPriorityError(
            f"Priority {candidate.priority} is already used by {duplicate.name} "
            f"for {candidate.target_device_type.value}.{candidate.action.value}. "
            "Choose a different priority so a target device cannot receive "
            "two equally ranked discrete actions."
        )

    same_room = [
        policy
        for policy in comparable
        if policy.target_scope == IoTTargetScope.SAME_ROOM
    ]
    facility = [
        policy
        for policy in comparable
        if policy.target_scope == IoTTargetScope.WHOLE_FACILITY
    ]

    if candidate.target_scope == IoTTargetScope.WHOLE_FACILITY and same_room:
        highest_same_room = max(policy.priority for policy in same_room)
        if candidate.priority <= highest_same_room:
            raise IoTPolicyPriorityError(
                f"Whole-facility {candidate.target_device_type.value} policies must "
                f"have a priority higher than every same-room policy. Use a value "
                f"above {highest_same_room}."
            )

    if candidate.target_scope == IoTTargetScope.SAME_ROOM and facility:
        lowest_facility = min(policy.priority for policy in facility)
        if candidate.priority >= lowest_facility:
            raise IoTPolicyPriorityError(
                f"Same-room {candidate.target_device_type.value} policies must have "
                f"a priority lower than whole-facility policies. Use a value below "
                f"{lowest_facility}."
            )
