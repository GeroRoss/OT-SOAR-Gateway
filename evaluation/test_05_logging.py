"""Suite 05: normalized audit-log correctness and duplicate-event regression."""

import time, pytest

ADMIN = {"X-Actor-ID": "personnel-001"}


def reset(c, g):
    r = c.post(f"{g}/system/reset-demo-data")
    assert r.status_code == 200, r.text


def events(c, g, **params):
    q = [("limit", "300")]
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            q += [(k, x) for x in v]
        else:
            q.append((k, v))
    r = c.get(f"{g}/events", params=q)
    assert r.status_code == 200, r.text
    return r.json()


def newest_matching(es, pred):
    return next((e for e in es if pred(e)), None)


def assert_shape(e):
    for k in (
        "type",
        "actor",
        "action",
        "cause",
        "violation",
        "timestamp",
        "source_id",
        "metadata",
    ):
        assert k in e


@pytest.mark.scenario(
    id="LOG-01",
    description="Management log contains actor, target/action and cause",
    expected="Authorized room creation produces a normalized Management event with human actor and management cause.",
)
def test_management_event_fields(client, gateway_url):
    reset(client, gateway_url)
    r = client.post(
        f"{gateway_url}/rooms", headers=ADMIN, json={"name": "Logging Room"}
    )
    assert r.status_code == 201, r.text
    rid = r.json()["room_id"]
    e = newest_matching(
        events(client, gateway_url, type=["Management"], source_id=rid),
        lambda x: x.get("metadata", {}).get("event_type") == "room_registered",
    )
    assert e
    assert_shape(e)
    assert (
        e["actor"] == "John Smith"
        and "Create Room" in e["action"]
        and e["cause"]
        and e["violation"] is None
    )


@pytest.mark.scenario(
    id="LOG-02",
    description="ABAC denial log identifies actor, target action, cause and violation",
    expected="Denied manual control is represented once as Security with ABAC Denied and an explanatory cause.",
)
def test_abac_denial_log_fields(client, gateway_url):
    reset(client, gateway_url)
    r = client.post(
        f"{gateway_url}/devices/door-001/commands/door",
        json={"person_id": "personnel-004", "command": {"locked": False}},
    )
    assert r.status_code == 403
    es = events(client, gateway_url, type=["Security"], source_id="door-001")
    matches = [
        e
        for e in es
        if e.get("metadata", {}).get("event_type") == "control_permission_violation"
    ]
    assert len(matches) == 1, matches
    e = matches[0]
    assert_shape(e)
    assert (
        e["actor"] == "Olivia Wilson"
        and e["violation"] == "ABAC Denied"
        and e["cause"]
        and "Denied" in e["action"]
    )


@pytest.mark.scenario(
    id="LOG-03",
    description="Allowed and denied door access are distinguishable and denial is not duplicated",
    expected="Allowed request is Control; denied request is represented by one authoritative Security event for the logical ABAC decision.",
)
def test_door_allowed_denied_and_no_duplicate(client, gateway_url):
    reset(client, gateway_url)
    assert (
        client.post(
            f"{gateway_url}/access/doors/door-001", json={"person_id": "personnel-006"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{gateway_url}/access/doors/door-001", json={"person_id": "personnel-007"}
        ).status_code
        == 403
    )
    es = events(client, gateway_url, source_id="door-001", type=["Control", "Security"])
    allowed = [
        e
        for e in es
        if e.get("metadata", {}).get("event_type") == "door_access_allowed"
    ]
    denied = [
        e
        for e in es
        if e.get("actor") in ("Lucifer Morningstar", "personnel-007")
        and e.get("type") == "Security"
    ]
    assert len(allowed) == 1, allowed
    assert len(denied) == 1, denied
    assert "Allowed" in allowed[0]["action"] and "Denied" in denied[0]["action"]


@pytest.mark.scenario(
    id="LOG-04",
    description="IoT policy response is auditable",
    expected="Environmental orchestration produces a Control event identifying policy action and target context.",
)
def test_iot_policy_action_logged(client, gateway_url):
    reset(client, gateway_url)
    r = client.put(
        f"{gateway_url}/simulation/environments/room-001",
        json={"temperature": 45, "humidity": 40, "smoke_level": 0},
    )
    assert r.status_code == 200
    end = time.monotonic() + 8
    found = None
    while time.monotonic() < end:
        found = newest_matching(
            events(client, gateway_url, type=["Control"]),
            lambda e: e.get("metadata", {}).get("event_type") == "iot_policy_action"
            and e.get("source_id") == "hvac-001",
        )
        if found:
            break
        time.sleep(0.25)
    assert found
    assert_shape(found)
    assert found["action"] and found["cause"]


@pytest.mark.scenario(
    id="LOG-05",
    description="Normalized event filtering and timestamps are usable",
    expected="Type/source filters return only matching events and every returned event has a timestamp.",
)
def test_event_filters_and_timestamps(client, gateway_url):
    reset(client, gateway_url)
    client.post(
        f"{gateway_url}/devices/hvac-001/commands/hvac",
        json={"person_id": "personnel-004", "command": {"cooling_level": 35}},
    )
    es = events(client, gateway_url, type=["Control"], source_id="hvac-001")
    assert es
    assert all(
        e["type"] == "Control" and e["source_id"] == "hvac-001" and e["timestamp"]
        for e in es
    )
