"""Suite 01: basic management, seed/reset, CRUD and validation."""

import pytest

ADMIN = {"X-Actor-ID": "personnel-001"}
ENGINEER = {"X-Actor-ID": "personnel-002"}


def reset(c, g):
    r = c.post(f"{g}/system/reset-demo-data")
    assert r.status_code == 200, r.text


def by_id(items, key, value):
    return next((x for x in items if x[key] == value), None)


@pytest.mark.scenario(
    id="BASIC-01",
    description="Seed/reset restores reference data",
    expected="Seed rooms, devices, personnel, IoT policies and ABAC policies are available after reset.",
)
def test_seeded_reference_data(client, gateway_url):
    reset(client, gateway_url)
    assert by_id(client.get(f"{gateway_url}/rooms").json(), "room_id", "room-001")
    assert by_id(client.get(f"{gateway_url}/devices").json(), "device_id", "env-001")
    assert by_id(
        client.get(f"{gateway_url}/personnel").json(), "person_id", "personnel-001"
    )
    assert client.get(f"{gateway_url}/iot-policies").json()
    assert client.get(f"{gateway_url}/policies").json()


@pytest.mark.scenario(
    id="BASIC-02",
    description="Room CRUD works for an unreferenced room",
    expected="Authorized admin can create, read, update and delete a room.",
)
def test_room_crud(client, gateway_url):
    reset(client, gateway_url)
    r = client.post(
        f"{gateway_url}/rooms", headers=ADMIN, json={"name": "Evaluation Room"}
    )
    assert r.status_code == 201, r.text
    rid = r.json()["room_id"]
    assert client.get(f"{gateway_url}/rooms/{rid}").status_code == 200
    r = client.put(
        f"{gateway_url}/rooms/{rid}",
        headers=ADMIN,
        json={"name": "Updated Evaluation Room"},
    )
    assert r.status_code == 200 and r.json()["name"] == "Updated Evaluation Room"
    assert client.delete(f"{gateway_url}/rooms/{rid}", headers=ADMIN).status_code == 204
    assert client.get(f"{gateway_url}/rooms/{rid}").status_code == 404


@pytest.mark.scenario(
    id="BASIC-03",
    description="Device registry CRUD uses gateway-owned defaults",
    expected="Device ID/protocol/criticality are generated and stable while editable metadata can change.",
)
def test_device_crud_and_defaults(client, gateway_url):
    reset(client, gateway_url)
    r = client.post(
        f"{gateway_url}/devices",
        headers=ADMIN,
        json={
            "device_type": "environmental_sensor",
            "room_id": "room-001",
            "name": "Evaluation Sensor",
        },
    )
    assert r.status_code == 201, r.text
    d = r.json()
    did = d["device_id"]
    assert d["protocol"] == "mqtt" and d["security_state"] == "normal"
    r = client.put(
        f"{gateway_url}/devices/{did}",
        headers=ADMIN,
        json={"name": "Moved Evaluation Sensor", "room_id": "room-002"},
    )
    assert r.status_code == 200, r.text
    d2 = r.json()
    assert (
        d2["device_id"] == did
        and d2["device_type"] == d["device_type"]
        and d2["protocol"] == d["protocol"]
        and d2["room_id"] == "room-002"
    )
    assert (
        client.delete(f"{gateway_url}/devices/{did}", headers=ADMIN).status_code == 204
    )


@pytest.mark.scenario(
    id="BASIC-04",
    description="Personnel create/read/update and validation work",
    expected="Authorized admin can create/update personnel; invalid room references are rejected.",
)
def test_personnel_management_and_validation(client, gateway_url):
    reset(client, gateway_url)
    payload = {
        "name": "Evaluation Technician",
        "role": "technician",
        "clearance": 2,
        "authorized_rooms": ["room-001"],
        "active": True,
    }
    r = client.post(f"{gateway_url}/personnel", headers=ADMIN, json=payload)
    assert r.status_code == 201, r.text
    pid = r.json()["person_id"]
    assert client.get(f"{gateway_url}/personnel/{pid}").status_code == 200
    payload.update(name="Updated Technician", active=False)
    r = client.put(f"{gateway_url}/personnel/{pid}", headers=ADMIN, json=payload)
    assert r.status_code == 200 and r.json()["active"] is False
    bad = dict(payload, authorized_rooms=["room-does-not-exist"])
    assert (
        client.post(f"{gateway_url}/personnel", headers=ADMIN, json=bad).status_code
        == 400
    )


@pytest.mark.scenario(
    id="BASIC-05",
    description="IoT policy CRUD and enable-disable work",
    expected="Engineering/admin account can create, read through collection, update/disable and delete an IoT policy.",
)
def test_iot_policy_crud(client, gateway_url):
    reset(client, gateway_url)
    p = {
        "name": "Evaluation cooling policy",
        "enabled": True,
        "trigger_device_type": "environmental_sensor",
        "trigger_attribute": "temperature",
        "operator": "greater_than_or_equal",
        "threshold": 33,
        "required_source_state": "normal",
        "target_device_type": "hvac",
        "target_scope": "same_room",
        "action": "set_cooling",
        "action_value": 77,
        "fallback_value": 35,
        "priority": 8,
    }
    r = client.post(f"{gateway_url}/iot-policies", headers=ENGINEER, json=p)
    assert r.status_code == 201, r.text
    pid = r.json()["policy_id"]
    assert by_id(client.get(f"{gateway_url}/iot-policies").json(), "policy_id", pid)
    p.update(name="Disabled evaluation cooling policy", enabled=False)
    r = client.put(f"{gateway_url}/iot-policies/{pid}", headers=ENGINEER, json=p)
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert (
        client.delete(f"{gateway_url}/iot-policies/{pid}", headers=ENGINEER).status_code
        == 204
    )


@pytest.mark.scenario(
    id="BASIC-06",
    description="ABAC policy CRUD and enable-disable work",
    expected="OT Administrator can create, read, update/disable and delete an ABAC policy.",
)
def test_abac_policy_crud(client, gateway_url):
    reset(client, gateway_url)
    p = {
        "name": "Evaluation ABAC rule",
        "enabled": True,
        "effect": "allow",
        "action": "control_hvac",
        "subject_type": "personnel",
        "subject_roles": ["ot_administrator"],
        "minimum_clearance": 5,
        "subject_device_type": None,
        "resource_type": "device",
        "resource_device_type": "hvac",
        "require_same_room": False,
        "allowed_subject_security_states": None,
        "allowed_resource_security_states": ["normal", "suspicious"],
        "start_hour": None,
        "end_hour": None,
        "priority": 8,
    }
    r = client.post(f"{gateway_url}/policies", headers=ADMIN, json=p)
    assert r.status_code == 201, r.text
    pol = r.json()
    pid = pol["policy_id"]
    assert client.get(f"{gateway_url}/policies/{pid}").status_code == 200
    pol.update(name="Disabled Evaluation ABAC rule", enabled=False)
    r = client.put(f"{gateway_url}/policies/{pid}", headers=ADMIN, json=pol)
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert (
        client.delete(f"{gateway_url}/policies/{pid}", headers=ADMIN).status_code == 204
    )
