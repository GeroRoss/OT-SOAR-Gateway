"""Suite 09: end-to-end integration incidents.

These scenarios intentionally compose attack generation, ABAC/detection,
state transition, response selection, physical state, audit evidence,
availability and recovery.
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


def wait_for_response(client, gateway_url, device_id, strategy=None, timeout=8.0):
    def lookup():
        r = client.get(
            f"{gateway_url}/responses", params={"device_id": device_id, "limit": 20}
        )
        assert r.status_code == 200, r.text
        for item in r.json():
            if strategy is None or item["strategy"] == strategy:
                return item
        return None

    return wait_until(
        lookup, timeout=timeout, description=f"mitigation response for {device_id}"
    )


def launch_attack(client, gateway_url, device_id, attack_type, rate=20, duration=2):
    r = client.post(
        f"{gateway_url}/attack/launch",
        json={
            "device_id": device_id,
            "attack_type": attack_type,
            "rate_per_second": rate,
            "duration_seconds": duration,
        },
    )
    assert r.status_code == 202, r.text
    return r.json()["attack_id"]


def wait_attack(client, gateway_url, attack_id, timeout=10):
    def finished():
        r = client.get(f"{gateway_url}/attack/status")
        assert r.status_code == 200, r.text
        item = next((x for x in r.json() if x["attack_id"] == attack_id), None)
        return (
            item
            if item and item["status"] in {"completed", "failed", "cancelled"}
            else None
        )

    return wait_until(finished, timeout=timeout, description=attack_id)


@pytest.mark.scenario(
    id="INT-01",
    description="Telemetry-flood incident is detected, contained, audited and recoverable",
    expected="A flood drives env-001 to quarantine, creates logical containment, leaves room-002 operational, and can be reset by an authorized administrator.",
)
def test_flood_full_incident_lifecycle(client, gateway_url):
    reset(client, gateway_url)

    attack_id = launch_attack(
        client, gateway_url, "env-001", "telemetry_flood", rate=20, duration=2
    )
    attack = wait_attack(client, gateway_url, attack_id)
    assert attack["status"] == "completed"

    wait_until(
        lambda: (
            s
            if (s := security(client, gateway_url, "env-001"))["security_state"]
            == "quarantined"
            else None
        ),
        description="env-001 quarantine",
    )
    mitigation = wait_for_response(
        client, gateway_url, "env-001", "logical_containment"
    )
    assert mitigation["success"] is True

    # Availability outside the attacked device/room is preserved.
    healthy = client.post(
        f"{gateway_url}/devices/pdu-002/commands/pdu",
        json={"person_id": "personnel-004", "command": {"power_on": True}},
    )
    assert healthy.status_code == 200, healthy.text

    ev = client.get(
        f"{gateway_url}/events",
        params={"type": "Security", "source_id": "env-001", "limit": 100},
    )
    assert ev.status_code == 200
    assert any(
        item.get("state") in {"Suspicious → Quarantined", "Normal → Quarantined"}
        for item in ev.json()
    )

    recovered = client.post(
        f"{gateway_url}/security/devices/env-001/reset",
        headers={"X-Actor-ID": "personnel-001"},
    )
    assert recovered.status_code == 200
    assert recovered.json()["security_state"] == "normal"


@pytest.mark.scenario(
    id="INT-02",
    description="Quarantined PDU during smoke emergency selects physical power isolation",
    expected="When room smoke is already at emergency level, PDU quarantine selects emergency_power_isolation and leaves the room power unavailable.",
)
def test_security_incident_interacts_with_safety_context(client, gateway_url):
    reset(client, gateway_url)

    # Establish physical safety context directly in the development simulator.
    r = client.put(
        f"{gateway_url}/simulation/environments/room-001", json={"smoke_level": 30}
    )
    assert r.status_code == 200, r.text

    force_device_quarantine_by_violations(client, gateway_url, "pdu-001")
    mitigation = wait_for_response(
        client, gateway_url, "pdu-001", "emergency_power_isolation"
    )
    assert mitigation["success"] is True
    assert mitigation["safety_context"]["smoke_level"] >= 20

    wait_until(
        lambda: (
            state
            if (state := operational_state(client, gateway_url, "pdu-001"))[
                "environment"
            ]["power_available"]
            is False
            else None
        ),
        description="emergency PDU power isolation",
    )

    # Another room remains usable despite the room-001 safety/security incident.
    healthy = client.post(
        f"{gateway_url}/devices/pdu-002/commands/pdu",
        json={"person_id": "personnel-004", "command": {"power_on": True}},
    )
    assert healthy.status_code == 200, healthy.text


@pytest.mark.scenario(
    id="INT-03",
    description="Quarantined door during smoke emergency preserves egress",
    expected="A door-controller security incident under smoke conditions selects emergency egress rather than the normal secure-lock response.",
)
def test_door_security_incident_preserves_emergency_egress(client, gateway_url):
    reset(client, gateway_url)

    r = client.put(
        f"{gateway_url}/simulation/environments/room-001", json={"smoke_level": 30}
    )
    assert r.status_code == 200, r.text

    force_device_quarantine_by_violations(client, gateway_url, "door-001")
    mitigation = wait_for_response(client, gateway_url, "door-001", "emergency_egress")
    assert mitigation["success"] is True

    wait_until(
        lambda: (
            state
            if (state := operational_state(client, gateway_url, "door-001"))["locked"]
            is False
            else None
        ),
        description="emergency door unlock",
    )
