"""Suite 06: sliding-window thresholds and security-state transitions.

Controlled messages and denied requests isolate detector behavior.
Attack-generator scenarios are covered in Suite 07."""

from __future__ import annotations

import time

import pytest

ADMIN = {"X-Actor-ID": "personnel-001"}
DEVICE_ID = "env-001"
PDU_ID = "pdu-001"


def reset_system(client, gateway_url):
    response = client.post(f"{gateway_url}/system/reset-demo-data")
    assert response.status_code == 200, response.text
    # Give reset/reconciliation a short period to settle.
    time.sleep(0.5)


def detector_config(client, gateway_url):
    response = client.get(f"{gateway_url}/security/config")
    assert response.status_code == 200, response.text
    return response.json()


def security_status(client, gateway_url, device_id=DEVICE_ID):
    response = client.get(f"{gateway_url}/security/devices/{device_id}")
    assert response.status_code == 200, response.text
    return response.json()


def generate_policy_violation(client, gateway_url, source_device_id=DEVICE_ID):
    """Generate one genuine ABAC violation without using the attack API.

    env-001 is an environmental sensor, so attempting to control pdu-001 is
    outside its permitted device capability.  The gateway must deny the
    individual request and pass the violation to the detector.
    """
    response = client.post(
        f"{gateway_url}/devices/{PDU_ID}/commands/device/pdu",
        json={"source_device_id": source_device_id, "command": {"power_on": True}},
    )
    assert response.status_code == 403, response.text


def send_valid_pdu_telemetry(client, gateway_url):
    """Send one accepted HTTP PDU message for controlled message-rate testing."""
    response = client.post(
        f"{gateway_url}/telemetry/pdu",
        json={
            "device_id": PDU_ID,
            "room_id": "room-001",
            "voltage": 230.0,
            "current": 4.0,
            "power": 920.0,
            "power_on": True,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def wait_for_state(client, gateway_url, device_id, expected_state, timeout_seconds=5):
    deadline = time.monotonic() + timeout_seconds
    last = None

    while time.monotonic() < deadline:
        last = security_status(client, gateway_url, device_id)
        if last["security_state"] == expected_state:
            return last
        time.sleep(0.1)

    raise AssertionError(
        f"{device_id} did not reach {expected_state!r}. Last status: {last}"
    )


@pytest.mark.scenario(
    id="DET-01",
    description="Detector exposes its implemented configuration",
    expected=(
        "The API reports a 10-second rolling window, message thresholds 8/14, "
        "violation thresholds 2/4, a 20-second suspicious recovery period, "
        "and peer-integrity streak thresholds 4/3."
    ),
)
def test_detector_configuration(client, gateway_url):
    assert detector_config(client, gateway_url) == {
        "window_seconds": 10,
        "suspicious_message_threshold": 8,
        "quarantine_message_threshold": 14,
        "suspicious_violation_threshold": 2,
        "quarantine_violation_threshold": 4,
        "recovery_seconds": 20,
        "integrity_quarantine_streak": 4,
        "integrity_recovery_streak": 3,
    }


@pytest.mark.scenario(
    id="DET-02",
    description="One isolated ABAC violation stays below the suspicious threshold",
    expected=(
        "The request is denied and counted, but one violation does not move "
        "env-001 out of NORMAL."
    ),
)
def test_single_violation_remains_normal(client, gateway_url):
    reset_system(client, gateway_url)

    generate_policy_violation(client, gateway_url)
    status = security_status(client, gateway_url)

    assert status["security_state"] == "normal"
    assert status["policy_violation_count"] == 1


@pytest.mark.scenario(
    id="DET-03",
    description="Violation thresholds produce the documented state transitions",
    expected=(
        "Two violations inside the rolling window produce SUSPICIOUS; a third "
        "remains SUSPICIOUS; the fourth produces QUARANTINED."
    ),
)
def test_violation_threshold_boundaries(client, gateway_url):
    reset_system(client, gateway_url)

    generate_policy_violation(client, gateway_url)
    first = security_status(client, gateway_url)
    assert first["security_state"] == "normal"
    assert first["policy_violation_count"] == 1

    generate_policy_violation(client, gateway_url)
    second = security_status(client, gateway_url)
    assert second["security_state"] == "suspicious"
    assert second["policy_violation_count"] == 2

    generate_policy_violation(client, gateway_url)
    third = security_status(client, gateway_url)
    assert third["security_state"] == "suspicious"
    assert third["policy_violation_count"] == 3

    generate_policy_violation(client, gateway_url)
    fourth = security_status(client, gateway_url)
    assert fourth["security_state"] == "quarantined"
    assert fourth["policy_violation_count"] == 4


@pytest.mark.scenario(
    id="DET-04",
    description="Old evidence expires from the rolling window",
    expected=(
        "A single violation expires after the configured 10-second window; a "
        "later isolated violation is treated as a new count of one."
    ),
)
def test_sliding_window_expires_old_violation(client, gateway_url):
    reset_system(client, gateway_url)
    config = detector_config(client, gateway_url)

    generate_policy_violation(client, gateway_url)
    assert security_status(client, gateway_url)["policy_violation_count"] == 1

    time.sleep(config["window_seconds"] + 0.5)

    expired = security_status(client, gateway_url)
    assert expired["security_state"] == "normal"
    assert expired["policy_violation_count"] == 0

    generate_policy_violation(client, gateway_url)
    new_window = security_status(client, gateway_url)
    assert new_window["security_state"] == "normal"
    assert new_window["policy_violation_count"] == 1


@pytest.mark.scenario(
    id="DET-05",
    description="A suspicious device recovers after sufficiently clean behaviour",
    expected=(
        "Two controlled violations produce SUSPICIOUS. With no further "
        "threshold-level anomaly, the device eventually returns to NORMAL."
    ),
)
def test_suspicious_recovers_after_clean_period(client, gateway_url):
    reset_system(client, gateway_url)
    config = detector_config(client, gateway_url)

    generate_policy_violation(client, gateway_url)
    generate_policy_violation(client, gateway_url)

    suspicious = security_status(client, gateway_url)
    assert suspicious["security_state"] == "suspicious"

    # Do not continuously poll during this interval. get_status() itself
    # evaluates the detector and, while evidence remains above threshold,
    # refreshes last_anomaly_at. Waiting without polling therefore tests a
    # genuinely clean period.
    time.sleep(config["window_seconds"] + config["recovery_seconds"] + 1)

    recovered = security_status(client, gateway_url)
    assert recovered["security_state"] == "normal"
    assert recovered["policy_violation_count"] == 0


@pytest.mark.scenario(
    id="DET-06",
    description="Accepted-message volume also drives the sliding-window detector",
    expected=(
        "Rapid valid PDU telemetry reaches the configured message thresholds: "
        "at least 8 recent messages produce SUSPICIOUS and continued messages "
        "produce QUARANTINED."
    ),
)
def test_message_volume_thresholds(client, gateway_url):
    reset_system(client, gateway_url)

    # pdu-001 is registered for HTTP telemetry, so these are valid accepted
    # messages rather than malformed or unauthorized requests.
    for _ in range(8):
        send_valid_pdu_telemetry(client, gateway_url)

    suspicious = wait_for_state(client, gateway_url, PDU_ID, "suspicious")
    assert suspicious["message_count"] >= 8

    # Continue until quarantine. Background simulator telemetry, if present,
    # is legitimate detector input, so the assertion intentionally checks
    # the implemented threshold rather than requiring exactly fourteen calls.
    deadline = time.monotonic() + 5
    quarantined = None

    while time.monotonic() < deadline:
        current = security_status(client, gateway_url, PDU_ID)
        if current["security_state"] == "quarantined":
            quarantined = current
            break
        send_valid_pdu_telemetry(client, gateway_url)

    assert (
        quarantined is not None
    ), "pdu-001 did not reach QUARANTINED after continued accepted messages"
    assert quarantined["message_count"] >= 14


@pytest.mark.scenario(
    id="DET-07",
    description="Quarantine does not automatically expire",
    expected=(
        "After four violations env-001 remains QUARANTINED even after the "
        "rolling window has expired."
    ),
)
def test_quarantine_is_terminal_without_reset(client, gateway_url):
    reset_system(client, gateway_url)
    config = detector_config(client, gateway_url)

    for _ in range(4):
        generate_policy_violation(client, gateway_url)

    quarantined = security_status(client, gateway_url)
    assert quarantined["security_state"] == "quarantined"

    time.sleep(config["window_seconds"] + 0.5)

    still_quarantined = security_status(client, gateway_url)
    assert still_quarantined["security_state"] == "quarantined"


@pytest.mark.scenario(
    id="DET-08",
    description="Authorized manual recovery clears quarantine and detector history",
    expected=(
        "An authorized security reset returns a quarantined device to NORMAL "
        "and clears both rolling message and violation counts."
    ),
)
def test_manual_reset_clears_quarantine(client, gateway_url):
    reset_system(client, gateway_url)

    for _ in range(4):
        generate_policy_violation(client, gateway_url)

    assert security_status(client, gateway_url)["security_state"] == "quarantined"

    response = client.post(
        f"{gateway_url}/security/devices/{DEVICE_ID}/reset", headers=ADMIN
    )
    assert response.status_code == 200, response.text

    recovered = response.json()
    assert recovered["security_state"] == "normal"
    assert recovered["message_count"] == 0
    assert recovered["policy_violation_count"] == 0
