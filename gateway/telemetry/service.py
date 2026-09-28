"""Shared ingestion path for HTTP and MQTT telemetry."""

from fastapi import HTTPException
from statistics import median

from gateway.iot_policy.engine import (
    process_environmental_telemetry,
    process_pdu_telemetry,
    process_smoke_telemetry,
)
from gateway.policy.abac import authorize_device_telemetry
from gateway.registry import get_device, list_devices
from gateway.security.detector import detector
from gateway.telemetry.store import (
    environmental_telemetry,
    record_environmental,
    record_pdu,
    record_smoke,
)
from shared.devices import DeviceType, Protocol, SecurityState
from shared.policy import Action
from shared.telemetry import EnvironmentalTelemetry, PDUTelemetry, SmokeTelemetry


def _validate_transport(device_id: str, transport: Protocol) -> None:
    device = get_device(device_id)
    if device is None:
        raise HTTPException(status_code=403, detail="Unknown device")
    if device.protocol != transport:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Device {device_id} is registered for {device.protocol.value.upper()} "
                f"telemetry, not {transport.value.upper()}"
            ),
        )


def _discard_if_quarantined(device_id: str, transport: Protocol):
    """Enforce quarantine at the gateway trust boundary.

    Endpoints keep publishing while quarantined. The gateway acknowledges the
    transport delivery but discards the payload before ABAC, detector,
    telemetry storage, peer corroboration, or IoT-policy processing.
    """
    device = get_device(device_id)
    if device is not None and device.security_state == SecurityState.QUARANTINED:
        return {
            "status": "discarded",
            "device_id": device_id,
            "reason": "device_quarantined",
            "security_state": SecurityState.QUARANTINED.value,
            "transport": transport.value,
        }
    return None


# Compare with the first two same-room peers that have cached readings.
# Quarantined peers are excluded; Suspicious peers are still eligible.
# If the peers disagree, record uncertainty instead of identifying an outlier.
# Agreement can recover an integrity-only Suspicious state, never quarantine.
TEMPERATURE_PEER_AGREEMENT_C = 2.0
HUMIDITY_PEER_AGREEMENT_PERCENT = 8.0
TEMPERATURE_OUTLIER_C = 5.0
HUMIDITY_OUTLIER_PERCENT = 15.0
DANGEROUS_TEMPERATURE_C = 35.0


def _within_pair_tolerance(
    a: EnvironmentalTelemetry, b: EnvironmentalTelemetry
) -> bool:
    return (
        abs(a.temperature - b.temperature) <= TEMPERATURE_PEER_AGREEMENT_C
        and abs(a.humidity - b.humidity) <= HUMIDITY_PEER_AGREEMENT_PERCENT
    )


def _evaluate_peer_corroboration(telemetry: EnvironmentalTelemetry) -> None:
    candidates = [telemetry]

    for device in list_devices():
        if (
            device.device_id == telemetry.device_id
            or device.device_type != DeviceType.ENVIRONMENTAL_SENSOR
            or device.room_id != telemetry.room_id
            or device.security_state == SecurityState.QUARANTINED
        ):
            continue

        peer = environmental_telemetry.get(device.device_id)
        if peer is not None:
            candidates.append(peer)

    # Need the incoming reading and two peer readings before comparing.
    if len(candidates) < 3:
        return

    # The seeded room has three sensors. With extra sensors, registry order
    # decides which two peers are used; this is not a general voting scheme.
    peers = [item for item in candidates if item.device_id != telemetry.device_id][:2]
    if len(peers) < 2:
        return

    peer_a, peer_b = peers

    if not _within_pair_tolerance(peer_a, peer_b):
        detector.record_monitoring_uncertainty(
            telemetry.device_id,
            (
                f"Monitoring uncertainty in {telemetry.room_id}: "
                f"{peer_a.device_id}({peer_a.temperature:.1f}°C/{peer_a.humidity:.1f}%) "
                f"and {peer_b.device_id}({peer_b.temperature:.1f}°C/{peer_b.humidity:.1f}%). "
                "The two peers do not agree closely enough to identify a trustworthy majority; "
                "no device is automatically accused."
            ),
        )
        return

    reference_temperature = median([peer_a.temperature, peer_b.temperature])
    reference_humidity = median([peer_a.humidity, peer_b.humidity])
    temperature_delta = abs(telemetry.temperature - reference_temperature)
    humidity_delta = abs(telemetry.humidity - reference_humidity)

    is_outlier = (
        temperature_delta > TEMPERATURE_OUTLIER_C
        or humidity_delta > HUMIDITY_OUTLIER_PERCENT
    )

    if is_outlier:
        reasons = []
        if temperature_delta > TEMPERATURE_OUTLIER_C:
            reasons.append(
                f"temperature {telemetry.temperature:.1f} °C differs from "
                f"corroborated peer reference {reference_temperature:.1f} °C "
                f"by {temperature_delta:.1f} °C"
            )
        if humidity_delta > HUMIDITY_OUTLIER_PERCENT:
            reasons.append(
                f"humidity {telemetry.humidity:.1f}% differs from "
                f"corroborated peer reference {reference_humidity:.1f}% "
                f"by {humidity_delta:.1f} percentage points"
            )

        detector.record_integrity_disagreement(
            telemetry.device_id,
            "Possible slow telemetry poisoning or sensor fault: " + "; ".join(reasons),
        )
        return

    detector.record_integrity_agreement(
        telemetry.device_id,
        (
            f"{telemetry.device_id} is again consistent with corroborating "
            f"same-room sensors ({reference_temperature:.1f} °C / {reference_humidity:.1f}%)."
        ),
    )


def ingest_environmental(telemetry: EnvironmentalTelemetry, transport: Protocol):
    _validate_transport(telemetry.device_id, transport)
    discarded = _discard_if_quarantined(telemetry.device_id, transport)
    if discarded is not None:
        return discarded
    decision = authorize_device_telemetry(
        telemetry.device_id, telemetry.room_id, Action.PUBLISH_ENVIRONMENTAL_TELEMETRY
    )
    # Compare against independent same-room peers before the current reading
    # replaces its own cached value. The accepted reading is still retained as
    # evidence, while its resulting security state determines whether IoT
    # orchestration may trust it.
    _evaluate_peer_corroboration(telemetry)
    record_environmental(telemetry)
    detector_status = detector.record_message(telemetry.device_id)
    process_environmental_telemetry(telemetry, detector_status["security_state"])
    return {
        "status": "accepted",
        "device_id": telemetry.device_id,
        "policy_id": decision.policy_id,
        "security_state": detector_status["security_state"],
        "transport": transport.value,
    }


def ingest_smoke(telemetry: SmokeTelemetry, transport: Protocol):
    _validate_transport(telemetry.device_id, transport)
    discarded = _discard_if_quarantined(telemetry.device_id, transport)
    if discarded is not None:
        return discarded
    decision = authorize_device_telemetry(
        telemetry.device_id, telemetry.room_id, Action.PUBLISH_SMOKE_TELEMETRY
    )
    record_smoke(telemetry)
    detector_status = detector.record_message(telemetry.device_id)
    process_smoke_telemetry(telemetry, detector_status["security_state"])
    return {
        "status": "accepted",
        "device_id": telemetry.device_id,
        "policy_id": decision.policy_id,
        "security_state": detector_status["security_state"],
        "transport": transport.value,
    }


def ingest_pdu(telemetry: PDUTelemetry, transport: Protocol):
    _validate_transport(telemetry.device_id, transport)
    discarded = _discard_if_quarantined(telemetry.device_id, transport)
    if discarded is not None:
        return discarded
    decision = authorize_device_telemetry(
        telemetry.device_id, telemetry.room_id, Action.PUBLISH_PDU_TELEMETRY
    )
    record_pdu(telemetry)
    detector_status = detector.record_message(telemetry.device_id)
    process_pdu_telemetry(telemetry, detector_status["security_state"])
    return {
        "status": "accepted",
        "device_id": telemetry.device_id,
        "policy_id": decision.policy_id,
        "security_state": detector_status["security_state"],
        "transport": transport.value,
    }
