"""Suite 04: ABAC authorization and least-privilege enforcement."""

import pytest

ADMIN = {"X-Actor-ID": "personnel-001"}


def reset(c, g):
    r = c.post(f"{g}/system/reset-demo-data")
    assert r.status_code == 200, r.text


def denied(r):
    assert r.status_code == 403, r.text


@pytest.mark.scenario(
    id="ABAC-01",
    description="Routine operator permissions follow least privilege",
    expected="Facility Operator may control HVAC/PDU but may not perform privileged door override.",
)
def test_operator_routine_control_only(client, gateway_url):
    reset(client, gateway_url)
    assert (
        client.post(
            f"{gateway_url}/devices/hvac-001/commands/hvac",
            json={"person_id": "personnel-004", "command": {"cooling_level": 35}},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{gateway_url}/devices/pdu-001/commands/pdu",
            json={"person_id": "personnel-004", "command": {"power_on": True}},
        ).status_code
        == 200
    )
    denied(
        client.post(
            f"{gateway_url}/devices/door-001/commands/door",
            json={"person_id": "personnel-004", "command": {"locked": True}},
        )
    )


@pytest.mark.scenario(
    id="ABAC-02",
    description="Privileged security roles can override doors",
    expected="Security Operator with clearance 4 can manually control a door.",
)
def test_security_operator_door_override(client, gateway_url):
    reset(client, gateway_url)
    r = client.post(
        f"{gateway_url}/devices/door-001/commands/door",
        json={"person_id": "personnel-003", "command": {"locked": True}},
    )
    assert r.status_code == 200, r.text


@pytest.mark.scenario(
    id="ABAC-03",
    description="Unknown and inactive personnel fail closed",
    expected="Unknown and inactive identities receive HTTP 403.",
)
def test_unknown_and_inactive_fail_closed(client, gateway_url):
    reset(client, gateway_url)
    denied(
        client.post(
            f"{gateway_url}/devices/hvac-001/commands/hvac",
            json={"person_id": "no-such-person", "command": {"cooling_level": 35}},
        )
    )
    p = {
        "name": "Inactive Engineer",
        "role": "facility_engineer",
        "clearance": 4,
        "authorized_rooms": ["room-001"],
        "active": False,
    }
    r = client.post(f"{gateway_url}/personnel", headers=ADMIN, json=p)
    assert r.status_code == 201, r.text
    denied(
        client.post(
            f"{gateway_url}/devices/hvac-001/commands/hvac",
            json={"person_id": r.json()["person_id"], "command": {"cooling_level": 35}},
        )
    )


@pytest.mark.scenario(
    id="ABAC-04",
    description="Physical door access enforces authorized-room membership",
    expected="A low-clearance person authorized for room-001 may request access, while a visitor with no room authorization is denied.",
)
def test_door_access_room_membership(client, gateway_url):
    reset(client, gateway_url)
    assert (
        client.post(
            f"{gateway_url}/access/doors/door-001", json={"person_id": "personnel-006"}
        ).status_code
        == 200
    )
    denied(
        client.post(
            f"{gateway_url}/access/doors/door-001", json={"person_id": "personnel-007"}
        )
    )


@pytest.mark.scenario(
    id="ABAC-05",
    description="UI restrictions cannot be bypassed through direct management API calls",
    expected="Low-privilege personnel are denied direct personnel, IoT-policy and ABAC-policy modification requests.",
)
def test_low_privilege_direct_api_management_denied(client, gateway_url):
    reset(client, gateway_url)
    low = {"X-Actor-ID": "personnel-004"}
    person = client.get(f"{gateway_url}/personnel/personnel-004").json()
    person["clearance"] = 5
    denied(
        client.put(
            f"{gateway_url}/personnel/personnel-004",
            headers=low,
            json={
                k: person[k]
                for k in ("name", "role", "clearance", "authorized_rooms", "active")
            },
        )
    )
    iot = client.get(f"{gateway_url}/iot-policies").json()[0]
    body = {k: v for k, v in iot.items() if k != "policy_id"}
    denied(
        client.put(
            f"{gateway_url}/iot-policies/{iot['policy_id']}", headers=low, json=body
        )
    )
    abac = client.get(f"{gateway_url}/policies").json()[0]
    denied(
        client.put(
            f"{gateway_url}/policies/{abac['policy_id']}", headers=low, json=abac
        )
    )


@pytest.mark.scenario(
    id="ABAC-06",
    description="Device type authorization prevents lateral actuator control",
    expected="Environmental sensor cannot directly command a PDU or HVAC.",
)
def test_device_type_control_denied(client, gateway_url):
    reset(client, gateway_url)
    denied(
        client.post(
            f"{gateway_url}/devices/pdu-001/commands/device/pdu",
            json={"source_device_id": "env-001", "command": {"power_on": False}},
        )
    )


@pytest.mark.scenario(
    id="ABAC-07",
    description="Same-room telemetry authorization blocks cross-room identity use",
    expected="A registered device reporting another room is denied by ABAC.",
)
def test_device_cross_room_telemetry_denied(client, gateway_url):
    reset(client, gateway_url)
    r = client.post(
        f"{gateway_url}/telemetry/environmental",
        json={
            "device_id": "env-001",
            "room_id": "room-002",
            "temperature": 24,
            "humidity": 40,
        },
    )
    denied(r)


@pytest.mark.scenario(
    id="ABAC-08",
    description="Management endpoints require actor identity",
    expected="Direct management request without X-Actor-ID fails closed.",
)
def test_management_requires_actor(client, gateway_url):
    reset(client, gateway_url)
    denied(client.post(f"{gateway_url}/rooms", json={"name": "Unauthorized Room"}))
