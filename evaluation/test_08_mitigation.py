"""Suite 08: device-aware mitigation.

The detector is not under test here. Each case deliberately drives a device
to the already-defined quarantine threshold, then evaluates the response
engine's device-specific containment/safety action.
"""

import time
import pytest


def reset(client, gateway_url):
    r = client.post(f"{gateway_url}/system/reset-demo-data")
    assert r.status_code == 200, r.text
    time.sleep(0.6)


def security(client, gateway_url, device_id):
    r = client.get(f"{gateway_url}/security/devices/{device_id}")
    assert r.status_code == 200, r.text
    return r.json()


def operational_state(client, gateway_url, device_id):
    r = client.get(f"{gateway_url}/devices/{device_id}/operational-state")
    assert r.status_code == 200, r.text
    return r.json()


def wait_until(predicate, timeout=8.0, interval=0.1, description="condition"):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting for {description}; last={last}")


def force_device_quarantine_by_violations(client, gateway_url, source_device_id):
    """Generate four denied device-originated commands.

    The current ABAC baseline has no allow policy for device-originated
    actuator control. Four violations inside the 10 s detector window are the
    configured quarantine threshold.
    """
    for _ in range(4):
        r = client.post(
            f"{gateway_url}/devices/pdu-002/commands/device/pdu",
            json={"source_device_id": source_device_id, "command": {"power_on": False}},
        )
        assert r.status_code == 403, r.text

    def quarantined_status():
        status = security(client, gateway_url, source_device_id)
        if status["security_state"] == "quarantined":
            return status
        return None

    return wait_until(quarantined_status, description=f"{source_device_id} quarantine")


def wait_for_response(
    client, gateway_url, device_id, strategy=None, *, action_contains=None, timeout=8.0
):
    """Wait for the specific response the scenario is trying to evaluate.

    A device can now produce both a SUSPICIOUS observation response and a later
    QUARANTINED mitigation response.  Environmental sensors use logical
    containment for both stages, so strategy alone is not sufficient to
    distinguish them.
    """

    def lookup():
        r = client.get(
            f"{gateway_url}/responses", params={"device_id": device_id, "limit": 20}
        )
        assert r.status_code == 200, r.text
        for item in r.json():
            if strategy is not None and item["strategy"] != strategy:
                continue
            if action_contains is not None and action_contains not in item["action"]:
                continue
            return item
        return None

    return wait_until(
        lookup, timeout=timeout, description=f"mitigation response for {device_id}"
    )


@pytest.mark.scenario(
    id="MIT-01",
    description="Quarantined environmental sensor is logically contained",
    expected="The sensor is quarantined and receives logical containment rather than an actuator fail-safe.",
)
def test_sensor_quarantine_uses_logical_containment(client, gateway_url):
    reset(client, gateway_url)
    force_device_quarantine_by_violations(client, gateway_url, "env-001")

    response = wait_for_response(
        client,
        gateway_url,
        "env-001",
        "logical_containment",
        action_contains="Stop trusting sensor telemetry",
    )
    assert response["success"] is True
    assert "Stop trusting sensor telemetry" in response["action"]

    # Quarantined device-originated actions remain blocked.
    denied = client.post(
        f"{gateway_url}/devices/pdu-001/commands/device/pdu",
        json={"source_device_id": "env-001", "command": {"power_on": False}},
    )
    assert denied.status_code == 403


@pytest.mark.scenario(
    id="MIT-02",
    description="Quarantined HVAC enters fail-safe cooling",
    expected="HVAC quarantine commands 100% cooling and blocks subsequent normal personnel control.",
)
def test_hvac_quarantine_forces_fail_safe_cooling(client, gateway_url):
    reset(client, gateway_url)
    force_device_quarantine_by_violations(client, gateway_url, "hvac-001")

    response = wait_for_response(client, gateway_url, "hvac-001", "fail_safe_cooling")
    assert response["success"] is True

    def cooling_is_safe():
        state = operational_state(client, gateway_url, "hvac-001")
        return state if state["environment"]["cooling_level"] == 100 else None

    wait_until(cooling_is_safe, description="HVAC 100% fail-safe cooling")

    blocked = client.post(
        f"{gateway_url}/devices/hvac-001/commands/hvac",
        json={"person_id": "personnel-001", "command": {"cooling_level": 35}},
    )
    assert blocked.status_code == 403


@pytest.mark.scenario(
    id="MIT-03",
    description="Quarantined PDU preserves power without a smoke emergency",
    expected="With no smoke emergency, PDU quarantine preserves current power to avoid creating an outage.",
)
def test_pdu_quarantine_preserves_safe_operation(client, gateway_url):
    reset(client, gateway_url)

    before = operational_state(client, gateway_url, "pdu-001")
    assert before["environment"]["power_available"] is True

    force_device_quarantine_by_violations(client, gateway_url, "pdu-001")
    response = wait_for_response(
        client, gateway_url, "pdu-001", "preserve_safe_operation"
    )
    assert response["success"] is True

    after = operational_state(client, gateway_url, "pdu-001")
    assert after["environment"]["power_available"] is True

    blocked = client.post(
        f"{gateway_url}/devices/pdu-001/commands/pdu",
        json={"person_id": "personnel-001", "command": {"power_on": False}},
    )
    assert blocked.status_code == 403


@pytest.mark.scenario(
    id="MIT-04",
    description="Quarantined door controller enters secure state without smoke",
    expected="Without a smoke emergency, the quarantined door is locked and normal manual override is blocked.",
)
def test_door_quarantine_locks_securely(client, gateway_url):
    reset(client, gateway_url)

    # Put the door in an unlocked state first so mitigation must visibly change it.
    unlock = client.post(
        f"{gateway_url}/devices/door-001/commands/door",
        json={"person_id": "personnel-001", "command": {"locked": False}},
    )
    assert unlock.status_code == 200, unlock.text
    assert operational_state(client, gateway_url, "door-001")["locked"] is False

    force_device_quarantine_by_violations(client, gateway_url, "door-001")
    response = wait_for_response(client, gateway_url, "door-001", "secure_door")
    assert response["success"] is True

    wait_until(
        lambda: (
            state
            if (state := operational_state(client, gateway_url, "door-001"))["locked"]
            is True
            else None
        ),
        description="door secure lock",
    )

    blocked = client.post(
        f"{gateway_url}/devices/door-001/commands/door",
        json={"person_id": "personnel-001", "command": {"locked": False}},
    )
    assert blocked.status_code == 403


@pytest.mark.scenario(
    id="MIT-05",
    description="Quarantining one device does not disable unrelated rooms",
    expected="A quarantined room-001 device does not prevent authorized control of a healthy room-002 actuator.",
)
def test_quarantine_preserves_unrelated_room_availability(client, gateway_url):
    reset(client, gateway_url)
    force_device_quarantine_by_violations(client, gateway_url, "env-001")
    wait_for_response(client, gateway_url, "env-001", "logical_containment")

    r = client.post(
        f"{gateway_url}/devices/pdu-002/commands/pdu",
        json={"person_id": "personnel-004", "command": {"power_on": True}},
    )
    assert r.status_code == 200, r.text
    assert security(client, gateway_url, "pdu-002")["security_state"] == "normal"


@pytest.mark.scenario(
    id="MIT-06",
    description="Authorized recovery clears quarantine",
    expected="A privileged manual security reset returns the contained device to NORMAL with cleared detector counts.",
)
def test_authorized_recovery_after_mitigation(client, gateway_url):
    reset(client, gateway_url)
    force_device_quarantine_by_violations(client, gateway_url, "env-001")
    wait_for_response(client, gateway_url, "env-001", "logical_containment")

    r = client.post(
        f"{gateway_url}/security/devices/env-001/reset",
        headers={"X-Actor-ID": "personnel-001"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["security_state"] == "normal"
    assert body["message_count"] == 0
    assert body["policy_violation_count"] == 0
