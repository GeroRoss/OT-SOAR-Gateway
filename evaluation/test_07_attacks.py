"""Suite 07: attacks through the simulator and direct denied API requests.

ATTACK-04 replaces normal sensor publications with drifting values at the
same cadence, testing integrity detection without adding message-rate load."""

from __future__ import annotations

import time

import pytest

ADMIN = {"X-Actor-ID": "personnel-001"}
LOW_PRIVILEGE = {"X-Actor-ID": "personnel-004"}


def reset(client, gateway_url):
    response = client.post(f"{gateway_url}/system/reset-demo-data")
    assert response.status_code == 200, response.text
    time.sleep(0.5)


def security_status(client, gateway_url, device_id):
    response = client.get(f"{gateway_url}/security/devices/{device_id}")
    assert response.status_code == 200, response.text
    return response.json()


def launch_attack(
    client, gateway_url, device_id, attack_type, rate_per_second=20, duration_seconds=2
):
    response = client.post(
        f"{gateway_url}/attack/launch",
        json={
            "device_id": device_id,
            "attack_type": attack_type,
            "rate_per_second": rate_per_second,
            "duration_seconds": duration_seconds,
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "launched"
    return body["attack_id"]


def wait_attack_finished(client, gateway_url, attack_id, timeout=10):
    deadline = time.monotonic() + timeout
    last = None

    while time.monotonic() < deadline:
        response = client.get(f"{gateway_url}/attack/status")
        assert response.status_code == 200, response.text
        attacks = response.json()
        last = next(
            (attack for attack in attacks if attack["attack_id"] == attack_id), None
        )
        if last and last["status"] in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(0.1)

    raise AssertionError(
        f"Attack {attack_id} did not finish within {timeout}s; last={last}"
    )


def wait_security_state(client, gateway_url, device_id, expected_state, timeout=5):
    deadline = time.monotonic() + timeout
    last = None

    while time.monotonic() < deadline:
        last = security_status(client, gateway_url, device_id)
        if last["security_state"] == expected_state:
            return last
        time.sleep(0.1)

    raise AssertionError(f"{device_id} did not reach {expected_state}; last={last}")


def events(client, gateway_url, **params):
    response = client.get(f"{gateway_url}/events", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.scenario(
    id="ATTACK-01",
    description="High-rate telemetry flood is detected as a message-rate anomaly",
    expected=(
        "A compromised environmental sensor publishing at attack rate is "
        "accepted as the registered source but exceeds the rolling message "
        "threshold and reaches QUARANTINED."
    ),
)
def test_telemetry_flood_detected(client, gateway_url):
    reset(client, gateway_url)

    attack_id = launch_attack(
        client,
        gateway_url,
        "env-001",
        "telemetry_flood",
        rate_per_second=20,
        duration_seconds=2,
    )
    result = wait_attack_finished(client, gateway_url, attack_id)
    assert result["status"] == "completed"
    assert result["attempts"] == 40

    status = wait_security_state(client, gateway_url, "env-001", "quarantined")
    assert status["message_count"] >= 14

    security_events = events(
        client, gateway_url, type="Security", source_id="env-001", limit=100
    )
    assert any(event.get("state") == "Normal → Suspicious" for event in security_events)
    assert any(
        event.get("state") in {"Suspicious → Quarantined", "Normal → Quarantined"}
        for event in security_events
    )


@pytest.mark.scenario(
    id="ATTACK-02",
    description="Wrong-room telemetry from a compromised device is blocked and detected",
    expected=(
        "env-001 cannot publish using room-002 context. Repeated cross-room "
        "attempts generate ABAC violations and escalate the source to QUARANTINED."
    ),
)
def test_cross_room_compromise_blocked_and_detected(client, gateway_url):
    reset(client, gateway_url)

    attack_id = launch_attack(
        client,
        gateway_url,
        "env-001",
        "wrong_room",
        rate_per_second=5,
        duration_seconds=1,
    )
    result = wait_attack_finished(client, gateway_url, attack_id)
    assert result["status"] == "completed"
    assert result["attempts"] == 5

    status = wait_security_state(client, gateway_url, "env-001", "quarantined")
    assert status["policy_violation_count"] >= 4

    security_events = events(
        client, gateway_url, type="Security", source_id="env-001", limit=100
    )
    assert any(
        event.get("violation") == "Policy violation" for event in security_events
    )


@pytest.mark.scenario(
    id="ATTACK-03",
    description="Device-originated lateral actuator control is blocked and detected",
    expected=(
        "Repeated actuator commands originating from env-001 are denied by "
        "device ABAC. The attack simulator records denied attempts and the "
        "source device reaches QUARANTINED."
    ),
)
def test_unauthorized_device_control_blocked_and_detected(client, gateway_url):
    reset(client, gateway_url)

    attack_id = launch_attack(
        client,
        gateway_url,
        "env-001",
        "unauthorized_control",
        rate_per_second=5,
        duration_seconds=1,
    )
    result = wait_attack_finished(client, gateway_url, attack_id)
    assert result["status"] == "completed"
    assert result["attempts"] == 5
    assert result["denied_attempts"] == result["attempts"]
    assert result.get("target_device_id") is not None

    status = wait_security_state(client, gateway_url, "env-001", "quarantined")
    assert status["policy_violation_count"] >= 4


@pytest.mark.scenario(
    id="ATTACK-04",
    description="Slow environmental telemetry poisoning is detected by peer corroboration",
    expected=(
        "env-001 publishes at its normal cadence while its temperature drifts "
        "away from env-002 and env-003 in the same room. The first corroborated "
        "outlier moves env-001 to SUSPICIOUS; persistent disagreement reaches "
        "QUARANTINED without relying on the volumetric message-rate threshold. "
        "The two healthy peers remain NORMAL."
    ),
)
def test_slow_poisoning_detected_by_peer_corroboration(client, gateway_url):
    reset(client, gateway_url)

    # Allow all three room-001 environmental sensors to populate the gateway's
    # latest-telemetry cache before replacing env-001's normal publisher.
    time.sleep(3.0)

    attack_id = launch_attack(
        client,
        gateway_url,
        "env-001",
        "slow_poisoning",
        rate_per_second=1,  # ignored by the simulator for this normal-cadence attack
        duration_seconds=14,
    )

    # The drift is 1.5 C per 2-second sample. Once it exceeds the 5 C
    # outlier threshold, env-001 should enter the observation state.
    suspicious = wait_security_state(
        client, gateway_url, "env-001", "suspicious", timeout=12
    )
    assert suspicious["message_count"] < 8, (
        "Slow poisoning should be detected from peer disagreement before "
        "the volumetric suspicious threshold is reached."
    )
    assert suspicious["integrity_disagreement_streak"] >= 1

    result = wait_attack_finished(client, gateway_url, attack_id, timeout=20)
    assert result["status"] == "completed"
    assert result["attempts"] >= 7

    quarantined = wait_security_state(
        client, gateway_url, "env-001", "quarantined", timeout=5
    )
    assert quarantined["integrity_disagreement_streak"] >= 4

    # Device-specific containment: compromise of one sensor must not spread
    # security state to the two corroborating sensors.
    assert security_status(client, gateway_url, "env-002")["security_state"] == "normal"
    assert security_status(client, gateway_url, "env-003")["security_state"] == "normal"


@pytest.mark.scenario(
    id="ATTACK-05",
    description="Compromised low-privilege personnel cannot self-escalate",
    expected=(
        "Repeated attempts by personnel-004 to raise their own clearance are "
        "denied and the stored personnel record remains unchanged."
    ),
)
def test_personnel_self_privilege_escalation_blocked(client, gateway_url):
    reset(client, gateway_url)

    original_response = client.get(f"{gateway_url}/personnel/personnel-004")
    assert original_response.status_code == 200
    original = original_response.json()

    malicious_update = {
        "name": original["name"],
        "role": "ot_administrator",
        "clearance": 5,
        "authorized_rooms": original["authorized_rooms"],
        "active": original["active"],
    }

    for _ in range(4):
        response = client.put(
            f"{gateway_url}/personnel/personnel-004",
            headers=LOW_PRIVILEGE,
            json=malicious_update,
        )
        assert response.status_code == 403, response.text

    after = client.get(f"{gateway_url}/personnel/personnel-004").json()
    assert after["role"] == original["role"]
    assert after["clearance"] == original["clearance"]
    assert after["active"] == original["active"]

    audit = events(client, gateway_url, type="Security", limit=100)
    matching = [
        event
        for event in audit
        if (
            event.get("metadata", {}).get("event_type")
            == "management_permission_violation"
            and event.get("metadata", {}).get("resource_id") == "personnel-004"
        )
    ]
    assert len(matching) >= 4


@pytest.mark.scenario(
    id="ATTACK-06",
    description="Low-privilege personnel cannot tamper with security policies",
    expected=(
        "Direct hostile attempts to modify an IoT policy and an ABAC policy "
        "are denied, and the persisted policies remain unchanged."
    ),
)
def test_policy_tampering_by_low_privilege_personnel_blocked(client, gateway_url):
    reset(client, gateway_url)

    iot_policies = client.get(f"{gateway_url}/iot-policies").json()
    assert iot_policies
    iot_original = iot_policies[0]
    iot_payload = {
        key: value for key, value in iot_original.items() if key != "policy_id"
    }
    iot_payload["enabled"] = not iot_original["enabled"]

    response = client.put(
        f"{gateway_url}/iot-policies/{iot_original['policy_id']}",
        headers=LOW_PRIVILEGE,
        json=iot_payload,
    )
    assert response.status_code == 403, response.text

    abac_policies = client.get(f"{gateway_url}/policies").json()
    assert abac_policies
    abac_original = abac_policies[0]
    abac_payload = dict(abac_original)
    abac_payload["enabled"] = not abac_original["enabled"]

    response = client.put(
        f"{gateway_url}/policies/{abac_original['policy_id']}",
        headers=LOW_PRIVILEGE,
        json=abac_payload,
    )
    assert response.status_code == 403, response.text

    iot_after = next(
        policy
        for policy in client.get(f"{gateway_url}/iot-policies").json()
        if policy["policy_id"] == iot_original["policy_id"]
    )
    abac_after = client.get(
        f"{gateway_url}/policies/{abac_original['policy_id']}"
    ).json()

    assert iot_after["enabled"] == iot_original["enabled"]
    assert abac_after["enabled"] == abac_original["enabled"]

    audit = events(client, gateway_url, type="Security", limit=100)
    denied_resources = {
        event.get("metadata", {}).get("resource_type")
        for event in audit
        if event.get("metadata", {}).get("event_type")
        == "management_permission_violation"
    }
    assert "iot_policy" in denied_resources
    assert "abac_policy" in denied_resources
