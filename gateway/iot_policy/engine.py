"""Evaluate automation rules and resolve demands for each target actuator."""

from collections import defaultdict
from threading import Lock

from gateway.activity.repository import add_activity_event
from gateway.integrations.simulator import (
    get_simulated_device_state_sync,
    send_door_command_sync,
    send_hvac_command_sync,
    send_pdu_command_sync,
)
from gateway.iot_policy.models import (
    IoTAction,
    IoTConditionOperator,
    IoTDevicePolicy,
    IoTTargetScope,
)
from gateway.iot_policy.repository import list_iot_device_policies
from gateway.registry import list_devices
from shared.commands import DoorCommand, HVACCommand, PDUCommand
from shared.devices import DeviceType, SecurityState
from shared.telemetry import EnvironmentalTelemetry, PDUTelemetry, SmokeTelemetry

_source_state: dict[str, dict[str, dict]] = defaultdict(dict)

_state_lock = Lock()

_missing_target_notices: set[tuple[str, str]] = set()


def clear_runtime_state() -> None:
    """Clear cached readings and warning state after a demo reset."""

    with _state_lock:
        _source_state.clear()
        _missing_target_notices.clear()


def process_environmental_telemetry(
    telemetry: EnvironmentalTelemetry, security_state: str
) -> None:
    _update_source(
        telemetry.device_id,
        telemetry.room_id,
        DeviceType.ENVIRONMENTAL_SENSOR,
        security_state,
        {"temperature": telemetry.temperature, "humidity": telemetry.humidity},
    )


def process_smoke_telemetry(telemetry: SmokeTelemetry, security_state: str) -> None:
    _update_source(
        telemetry.device_id,
        telemetry.room_id,
        DeviceType.SMOKE_SENSOR,
        security_state,
        {"smoke_level": telemetry.smoke_level},
    )


def process_pdu_telemetry(telemetry: PDUTelemetry, security_state: str) -> None:
    _update_source(
        telemetry.device_id,
        telemetry.room_id,
        DeviceType.PDU,
        security_state,
        {
            "voltage": telemetry.voltage,
            "current": telemetry.current,
            "power": telemetry.power,
            "power_on": 1.0 if telemetry.power_on else 0.0,
        },
    )


def _update_source(
    device_id: str,
    room_id: str,
    device_type: DeviceType,
    security_state: str,
    values: dict,
) -> None:
    """Cache latest accepted reading and evaluate reusable policies."""

    with _state_lock:
        _source_state[room_id][device_id] = {
            "device_id": device_id,
            "room_id": room_id,
            "device_type": device_type,
            "security_state": SecurityState(security_state),
            "values": dict(values),
        }

        snapshot = {
            source_room: {
                source_id: {
                    "device_id": source["device_id"],
                    "room_id": source["room_id"],
                    "device_type": source["device_type"],
                    "security_state": source["security_state"],
                    "values": dict(source["values"]),
                }
                for (source_id, source) in room_sources.items()
            }
            for (source_room, room_sources) in _source_state.items()
        }

    _evaluate_all(snapshot)


def _condition_matches(value: float, policy: IoTDevicePolicy) -> bool:
    threshold = float(policy.threshold)

    if policy.operator == IoTConditionOperator.GREATER_THAN:
        return value > threshold

    if policy.operator == IoTConditionOperator.GREATER_THAN_OR_EQUAL:
        return value >= threshold

    if policy.operator == IoTConditionOperator.LESS_THAN:
        return value < threshold

    if policy.operator == IoTConditionOperator.LESS_THAN_OR_EQUAL:
        return value <= threshold

    return value == threshold


def _matching_sources(policy: IoTDevicePolicy, sources: list[dict]) -> list[dict]:
    matches = []

    for source in sources:
        if source["device_type"] != policy.trigger_device_type:
            continue

        if source["security_state"] != policy.required_source_state:
            continue

        value = source["values"].get(policy.trigger_attribute.value)

        if value is None:
            continue

        matches.append({**source, "value": float(value)})

    return matches


def _evaluate_all(source_snapshot: dict[str, dict[str, dict]]) -> None:
    """Resolve policies globally so facility rules remain authoritative."""

    policies = [policy for policy in list_iot_device_policies() if policy.enabled]

    if not policies:
        return

    devices = [
        device
        for device in list_devices()
        if (device.security_state == SecurityState.NORMAL)
    ]

    device_names = {device.device_id: device.name for device in devices}

    all_sources = [
        source
        for room_sources in source_snapshot.values()
        for source in room_sources.values()
    ]

    for source in all_sources:
        source["device_name"] = device_names.get(
            source["device_id"], source["device_id"]
        )

    buckets: dict[tuple[str, IoTAction], dict] = {}

    for policy in policies:
        if policy.target_scope == IoTTargetScope.SAME_ROOM:
            for room_id, room_sources_map in source_snapshot.items():
                room_sources = list(room_sources_map.values())

                candidates = _matching_sources(policy, room_sources)

                if not candidates:
                    continue

                targets = [
                    device
                    for device in devices
                    if (
                        device.room_id == room_id
                        and device.device_type == policy.target_device_type
                    )
                ]

                _add_policy_to_buckets(
                    policy, candidates, targets, buckets, notice_scope=room_id
                )

        else:
            candidates = _matching_sources(policy, all_sources)

            if not candidates:
                continue

            targets = [
                device
                for device in devices
                if (device.device_type == policy.target_device_type)
            ]

            _add_policy_to_buckets(
                policy, candidates, targets, buckets, notice_scope="whole facility"
            )

    for bucket in buckets.values():
        _apply_bucket(bucket)


def _add_policy_to_buckets(
    policy: IoTDevicePolicy,
    sources: list[dict],
    targets: list,
    buckets: dict,
    notice_scope: str,
) -> None:
    condition_sources = [
        source for source in sources if _condition_matches(source["value"], policy)
    ]

    if condition_sources and not targets:
        notice_key = (policy.policy_id, notice_scope)

        if notice_key not in _missing_target_notices:
            _missing_target_notices.add(notice_key)

            trigger = condition_sources[0]

            cause = _describe_matches([(policy, [trigger])])

            add_activity_event(
                event_type="iot_policy_no_target",
                source_id=trigger["device_id"],
                room_id=trigger["room_id"],
                message=(
                    f"{policy.name} matched, "
                    f"but no eligible "
                    f"{policy.target_device_type.value} "
                    f"target exists in "
                    f"{notice_scope}."
                ),
                metadata={
                    "action_text": ("IoT Device Policy " "Has No Eligible Target"),
                    "cause": cause,
                    "policy_id": policy.policy_id,
                    "policy_name": policy.name,
                    "target_device_type": (policy.target_device_type.value),
                    "target_scope": (policy.target_scope.value),
                    "source_device_id": trigger["device_id"],
                    "source_device_name": trigger.get(
                        "device_name", trigger["device_id"]
                    ),
                    "source_attribute": (policy.trigger_attribute.value),
                    "source_value": trigger["value"],
                    "operator": policy.operator.value,
                    "threshold": policy.threshold,
                },
            )

    else:
        _missing_target_notices.discard((policy.policy_id, notice_scope))

    for target in targets:
        key = (target.device_id, policy.action)

        bucket = buckets.setdefault(
            key, {"target": target, "matched": [], "fallback": []}
        )

        if condition_sources:
            bucket["matched"].append((policy, condition_sources))

        elif policy.fallback_value is not None:
            # Keep the eligible observations that failed the condition.
            # This lets Cause explain why the fallback was selected.
            bucket["fallback"].append((policy, sources))


def _apply_bucket(bucket: dict) -> None:
    """Resolve the winning policy demand or fallback for one target/action."""

    target = bucket["target"]
    matched = bucket["matched"]
    fallback = bucket["fallback"]

    if not matched and not fallback:
        return

    action = matched[0][0].action if matched else fallback[0][0].action

    if action == IoTAction.SET_COOLING:
        if matched:
            desired = max(policy.action_value for policy, _ in matched)

            selected = [item for item in matched if item[0].action_value == desired]

            cause = _describe_matches(selected)
            metadata = _match_metadata(selected)

        else:
            # Select the policy and fallback together so the
            # displayed policy ID is the policy that actually
            # supplied the winning fallback value.
            selected_policy, selected_sources = max(
                (
                    (policy, sources)
                    for policy, sources in fallback
                    if policy.fallback_value is not None
                ),
                key=lambda item: (
                    item[0].fallback_value,
                    item[0].priority,
                    item[0].policy_id,
                ),
            )

            desired = selected_policy.fallback_value

            cause = f"No cooling policy matched; fallback: {int(desired)}%"

            metadata = _fallback_metadata([(selected_policy, selected_sources)])

        _set_hvac(target, int(desired), cause, metadata)
        return

    candidates = matched if matched else fallback

    selected_policy, selected_sources = sorted(
        candidates, key=lambda item: (item[0].priority, item[0].policy_id), reverse=True
    )[0]

    desired = (
        selected_policy.action_value if matched else selected_policy.fallback_value
    )

    if desired is None:
        return

    if matched:
        selected = [(selected_policy, selected_sources)]

        cause = _describe_matches(selected)
        metadata = _match_metadata(selected)

    else:
        if action == IoTAction.SET_POWER:
            fallback_text = "On" if bool(desired) else "Off"

        elif action == IoTAction.SET_LOCKED:
            fallback_text = "Locked" if bool(desired) else "Unlocked"

        else:
            fallback_text = str(desired)

        cause = (
            f"Failed to meet "
            f"{selected_policy.policy_id}; "
            f"fallback: {fallback_text}"
        )

        metadata = _fallback_metadata([(selected_policy, selected_sources)])

    if action == IoTAction.SET_POWER:
        _set_pdu(target, bool(desired), cause, metadata)

    elif action == IoTAction.SET_LOCKED:
        _set_door(target, bool(desired), cause, metadata)


_ATTRIBUTE_LABELS = {
    "temperature": "temperature",
    "humidity": "humidity",
    "smoke_level": "smoke level",
    "voltage": "voltage",
    "current": "current",
    "power": "power",
    "power_on": "power state",
}


_ATTRIBUTE_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "voltage": " V",
    "current": " A",
    "power": " W",
}


_OPERATOR_SYMBOLS = {
    IoTConditionOperator.GREATER_THAN: ">",
    IoTConditionOperator.GREATER_THAN_OR_EQUAL: ">=",
    IoTConditionOperator.LESS_THAN: "<",
    IoTConditionOperator.LESS_THAN_OR_EQUAL: "<=",
    IoTConditionOperator.EQUAL: "=",
}


def _format_source_value(attribute: str, value: float) -> str:
    if attribute == "power_on":
        return "On" if value >= 0.5 else "Off"

    unit = _ATTRIBUTE_UNITS.get(attribute, "")

    return f"{value:.1f}" f"{unit}"


def _policy_identity(policy: IoTDevicePolicy) -> str:
    return f"{policy.name} " f"({policy.policy_id})"


def _condition_text(policy: IoTDevicePolicy) -> str:
    attribute = policy.trigger_attribute.value

    label = _ATTRIBUTE_LABELS.get(attribute, attribute.replace("_", " "))

    threshold = _format_source_value(attribute, float(policy.threshold))

    return f"{label} " f"{_OPERATOR_SYMBOLS[policy.operator]} " f"{threshold}"


def _describe_source_cause(policy: IoTDevicePolicy, source: dict) -> str:
    name = source.get("device_name") or source["device_id"]

    attribute = policy.trigger_attribute.value

    label = _ATTRIBUTE_LABELS.get(attribute, attribute.replace("_", " "))

    return (
        f"{name} reported "
        f"{label} "
        f"{_format_source_value(attribute, source['value'])}"
    )


def _describe_matches(matches: list[tuple[IoTDevicePolicy, list[dict]]]) -> str:
    causes: list[str] = []

    for policy, sources in matches:
        for source in sources:
            text = (
                f"{_describe_source_cause(policy, source)}, "
                f"satisfying "
                f"{_condition_text(policy)} "
                f"for "
                f"{_policy_identity(policy)}"
            )

            if text not in causes:
                causes.append(text)

    return "; ".join(causes) or "IoT Device Policy " "condition matched"


def _match_metadata(matches: list[tuple[IoTDevicePolicy, list[dict]]]) -> dict:
    policies = []
    sources = []

    for policy, matched_sources in matches:
        policies.append(
            {
                "policy_id": policy.policy_id,
                "policy_name": policy.name,
                "trigger_attribute": (policy.trigger_attribute.value),
                "operator": policy.operator.value,
                "operator_symbol": _OPERATOR_SYMBOLS[policy.operator],
                "threshold": policy.threshold,
                "priority": policy.priority,
            }
        )

        for source in matched_sources:
            sources.append(
                {
                    "device_id": source["device_id"],
                    "device_name": source.get("device_name", source["device_id"]),
                    "room_id": source["room_id"],
                    "security_state": (source["security_state"].value),
                    "attribute": (policy.trigger_attribute.value),
                    "value": source["value"],
                }
            )

    return {"policies": policies, "trigger_sources": sources, "fallback": False}


def _fallback_metadata(fallbacks: list[tuple[IoTDevicePolicy, list[dict]]]) -> dict:
    policies = []
    sources = []

    for policy, eligible_sources in fallbacks:
        policies.append(
            {
                "policy_id": policy.policy_id,
                "policy_name": policy.name,
                "trigger_attribute": (policy.trigger_attribute.value),
                "operator": policy.operator.value,
                "operator_symbol": _OPERATOR_SYMBOLS[policy.operator],
                "threshold": policy.threshold,
                "priority": policy.priority,
                "fallback_value": policy.fallback_value,
            }
        )

        for source in eligible_sources:
            sources.append(
                {
                    "device_id": source["device_id"],
                    "device_name": source.get("device_name", source["device_id"]),
                    "room_id": source["room_id"],
                    "security_state": (source["security_state"].value),
                    "attribute": (policy.trigger_attribute.value),
                    "value": source["value"],
                    "condition_matched": False,
                }
            )

    return {"policies": policies, "trigger_sources": sources, "fallback": True}


def _set_hvac(target, desired: int, cause: str, metadata: dict) -> None:
    try:
        state = get_simulated_device_state_sync(target.device_id)

        environment = state.get("environment", state)

        current = int(environment.get("cooling_level", -1))

        if current == desired:
            return

        send_hvac_command_sync(target.device_id, HVACCommand(cooling_level=desired))

        action_text = (
            f"Set {target.name} " f"({target.device_id}) " f"Cooling to {desired}%"
        )

        add_activity_event(
            event_type="iot_policy_action",
            source_id=target.device_id,
            room_id=target.room_id,
            message=(f"{action_text}. " f"Cause: {cause}."),
            metadata={
                **metadata,
                "action_text": action_text,
                "cause": cause,
                "target_device_id": target.device_id,
                "target_device_name": target.name,
                "target_action": (IoTAction.SET_COOLING.value),
                "previous_value": current,
                "target_value": desired,
            },
        )

    except Exception as exc:
        print("[iot-policy] " f"failed to set HVAC " f"{target.device_id}: " f"{exc}")


def _set_pdu(target, desired: bool, cause: str, metadata: dict) -> None:
    try:
        state = get_simulated_device_state_sync(target.device_id)

        current = bool(
            state.get(
                "power_on", state.get("environment", {}).get("power_available", True)
            )
        )

        if current == desired:
            return

        send_pdu_command_sync(target.device_id, PDUCommand(power_on=desired))

        action_text = (
            f"Turn "
            f"{'On' if desired else 'Off'} "
            f"{target.name} "
            f"({target.device_id})"
        )

        add_activity_event(
            event_type="iot_policy_action",
            source_id=target.device_id,
            room_id=target.room_id,
            message=(f"{action_text}. " f"Cause: {cause}."),
            metadata={
                **metadata,
                "action_text": action_text,
                "cause": cause,
                "target_device_id": target.device_id,
                "target_device_name": target.name,
                "target_action": (IoTAction.SET_POWER.value),
                "previous_value": current,
                "target_value": desired,
            },
        )

    except Exception as exc:
        print("[iot-policy] " f"failed to set PDU " f"{target.device_id}: " f"{exc}")


def _set_door(target, desired_locked: bool, cause: str, metadata: dict) -> None:
    try:
        state = get_simulated_device_state_sync(target.device_id)

        current = bool(state.get("locked", True))

        if current == desired_locked:
            return

        send_door_command_sync(target.device_id, DoorCommand(locked=desired_locked))

        action_text = (
            f"{'Lock' if desired_locked else 'Unlock'} "
            f"{target.name} "
            f"({target.device_id})"
        )

        add_activity_event(
            event_type="iot_policy_action",
            source_id=target.device_id,
            room_id=target.room_id,
            message=(f"{action_text}. " f"Cause: {cause}."),
            metadata={
                **metadata,
                "action_text": action_text,
                "cause": cause,
                "target_device_id": target.device_id,
                "target_device_name": target.name,
                "target_action": (IoTAction.SET_LOCKED.value),
                "previous_value": current,
                "target_value": desired_locked,
            },
        )

    except Exception as exc:
        print("[iot-policy] " f"failed to set door " f"{target.device_id}: " f"{exc}")
