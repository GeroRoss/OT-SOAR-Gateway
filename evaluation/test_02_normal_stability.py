"""Suite 02: normal-operation stability.

Control experiment: no malicious activity and no deliberate environmental
disturbance. This verifies stable actuator state and absence of false security
escalation in the current implementation.
"""

import time
import pytest


def reset(client, gateway_url):
    r = client.post(f"{gateway_url}/system/reset-demo-data")
    assert r.status_code == 200, r.text
    time.sleep(0.5)


def operational_state(client, gateway_url, device_id):
    # Current gateway route; the gateway proxies the facility simulator.
    r = client.get(f"{gateway_url}/devices/{device_id}/operational-state")
    assert r.status_code == 200, r.text
    return r.json()


def environment_value(device_state, key):
    """HVAC/PDU state is represented through the room environment."""
    environment = device_state.get("environment")
    assert isinstance(
        environment, dict
    ), f"Expected `environment` in operational state, got: {device_state}"
    assert key in environment, f"Missing {key!r} in {environment}"
    return environment[key]


def direct_value(device_state, key):
    """Devices with get_state(), notably the door, return direct state fields."""
    assert key in device_state, f"Missing {key!r} in {device_state}"
    return device_state[key]


def security(client, gateway_url, device_id):
    r = client.get(f"{gateway_url}/security/devices/{device_id}")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.scenario(
    id="STABLE-01",
    description="Untouched facility actuators remain in their seeded safe baseline",
    expected="HVAC stays at 35%, PDU stays powered and the biometric door stays locked.",
)
def test_untouched_actuators_remain_stable(client, gateway_url):
    reset(client, gateway_url)

    before = {
        d: operational_state(client, gateway_url, d)
        for d in ("hvac-001", "pdu-001", "door-001")
    }
    time.sleep(5)
    after = {
        d: operational_state(client, gateway_url, d)
        for d in ("hvac-001", "pdu-001", "door-001")
    }

    assert environment_value(before["hvac-001"], "cooling_level") == 35
    assert environment_value(after["hvac-001"], "cooling_level") == 35
    assert environment_value(before["pdu-001"], "power_available") is True
    assert environment_value(after["pdu-001"], "power_available") is True
    assert direct_value(before["door-001"], "locked") is True
    assert direct_value(after["door-001"], "locked") is True


@pytest.mark.scenario(
    id="STABLE-02",
    description="Normal telemetry does not escalate a sensor",
    expected="Normal simulator telemetry leaves env-001 in NORMAL.",
)
def test_normal_telemetry_does_not_escalate(client, gateway_url):
    reset(client, gateway_url)
    time.sleep(5)
    assert security(client, gateway_url, "env-001")["security_state"] == "normal"


@pytest.mark.scenario(
    id="STABLE-03",
    description="Normal operation produces no false security transition",
    expected="Representative seeded devices remain NORMAL during an untouched observation period.",
)
def test_no_false_security_transition(client, gateway_url):
    reset(client, gateway_url)
    time.sleep(5)
    for device_id in ("env-001", "hvac-001", "pdu-001", "door-001"):
        assert security(client, gateway_url, device_id)["security_state"] == "normal"
