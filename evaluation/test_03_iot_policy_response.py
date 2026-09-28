"""Suite 03: legitimate IoT-policy orchestration.

Environmental conditions are changed through the current development simulator
API. Assertions use the current gateway operational-state endpoint. Security
attack behaviour is intentionally excluded from this suite.
"""

import time
import pytest


def reset(client, gateway_url):
    r = client.post(f"{gateway_url}/system/reset-demo-data")
    assert r.status_code == 200, r.text
    time.sleep(0.5)


def set_environment(client, gateway_url, room_id, **changes):
    # Current application route is PUT /simulation/environments/{room_id}.
    r = client.put(f"{gateway_url}/simulation/environments/{room_id}", json=changes)
    assert r.status_code == 200, r.text
    return r.json()


def operational_state(client, gateway_url, device_id):
    r = client.get(f"{gateway_url}/devices/{device_id}/operational-state")
    assert r.status_code == 200, r.text
    return r.json()


def environment_value(device_state, key):
    environment = device_state.get("environment")
    assert isinstance(
        environment, dict
    ), f"Expected `environment` in operational state, got: {device_state}"
    assert key in environment, f"Missing {key!r} in {environment}"
    return environment[key]


def direct_value(device_state, key):
    assert key in device_state, f"Missing {key!r} in {device_state}"
    return device_state[key]


def wait_for_environment_value(
    client, gateway_url, device_id, key, predicate, timeout=8
):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = environment_value(operational_state(client, gateway_url, device_id), key)
        if predicate(last):
            return last
        time.sleep(0.25)
    raise AssertionError(
        f"{device_id}.{key} did not reach expected condition; last={last}"
    )


def wait_for_direct_value(client, gateway_url, device_id, key, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = direct_value(operational_state(client, gateway_url, device_id), key)
        if predicate(last):
            return last
        time.sleep(0.25)
    raise AssertionError(
        f"{device_id}.{key} did not reach expected condition; last={last}"
    )


@pytest.mark.scenario(
    id="IOT-01",
    description="High temperature increases same-room HVAC cooling",
    expected="A legitimate 45C condition in room-001 raises hvac-001 to at least the seeded >=40C demand.",
)
def test_temperature_drives_hvac(client, gateway_url):
    reset(client, gateway_url)
    set_environment(
        client, gateway_url, "room-001", temperature=45, humidity=40, smoke_level=0
    )
    level = wait_for_environment_value(
        client, gateway_url, "hvac-001", "cooling_level", lambda x: x >= 70
    )
    assert level >= 70


@pytest.mark.scenario(
    id="IOT-02",
    description="High humidity increases HVAC demand",
    expected="A legitimate high-humidity condition raises same-room HVAC above its 35% baseline.",
)
def test_humidity_drives_hvac(client, gateway_url):
    reset(client, gateway_url)
    set_environment(
        client, gateway_url, "room-001", temperature=24, humidity=90, smoke_level=0
    )
    level = wait_for_environment_value(
        client, gateway_url, "hvac-001", "cooling_level", lambda x: x > 35
    )
    assert level > 35


@pytest.mark.scenario(
    id="IOT-03",
    description="Combined conditions use maximum HVAC demand",
    expected="When temperature and humidity policies both match, HVAC uses the greatest matching cooling demand.",
)
def test_maximum_matching_hvac_demand(client, gateway_url):
    reset(client, gateway_url)
    set_environment(
        client, gateway_url, "room-001", temperature=45, humidity=90, smoke_level=0
    )
    level = wait_for_environment_value(
        client, gateway_url, "hvac-001", "cooling_level", lambda x: x >= 70
    )
    assert level >= 70


@pytest.mark.scenario(
    id="IOT-04",
    description="IoT policy scope is room-local",
    expected="A room-002 temperature excursion does not command room-001 HVAC.",
)
def test_same_room_scope(client, gateway_url):
    reset(client, gateway_url)
    set_environment(
        client, gateway_url, "room-001", temperature=24, humidity=40, smoke_level=0
    )
    set_environment(
        client, gateway_url, "room-002", temperature=45, humidity=40, smoke_level=0
    )
    time.sleep(4)
    assert (
        environment_value(
            operational_state(client, gateway_url, "hvac-001"), "cooling_level"
        )
        == 35
    )


@pytest.mark.scenario(
    id="IOT-05",
    description="Fire condition coordinates safety actuators",
    expected="Severe room-001 smoke causes high HVAC response, PDU power isolation and emergency door unlock according to seeded policies.",
)
def test_fire_response(client, gateway_url):
    reset(client, gateway_url)
    set_environment(client, gateway_url, "room-001", smoke_level=95)

    # Current PDU simulator has no independent get_state(); its operational
    # state exposes room power as environment.power_available.
    assert (
        wait_for_environment_value(
            client, gateway_url, "pdu-001", "power_available", lambda x: x is False
        )
        is False
    )

    # BiometricDoorSimulator implements get_state(), so `locked` is top-level.
    assert (
        wait_for_direct_value(
            client, gateway_url, "door-001", "locked", lambda x: x is False
        )
        is False
    )

    assert (
        wait_for_environment_value(
            client, gateway_url, "hvac-001", "cooling_level", lambda x: x >= 70
        )
        >= 70
    )


@pytest.mark.scenario(
    id="IOT-06",
    description="HVAC recovers to fallback after environmental recovery",
    expected="After a non-emergency temperature excursion clears, HVAC returns to the 35% seeded fallback.",
)
def test_temperature_recovery(client, gateway_url):
    reset(client, gateway_url)
    set_environment(
        client, gateway_url, "room-001", temperature=45, humidity=40, smoke_level=0
    )
    wait_for_environment_value(
        client, gateway_url, "hvac-001", "cooling_level", lambda x: x > 35
    )

    set_environment(
        client, gateway_url, "room-001", temperature=24, humidity=40, smoke_level=0
    )
    assert (
        wait_for_environment_value(
            client, gateway_url, "hvac-001", "cooling_level", lambda x: x == 35
        )
        == 35
    )
