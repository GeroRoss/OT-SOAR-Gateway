"""Subscribe to MQTT telemetry and pass it through gateway ingestion.

Demo reset stops and joins the subscriber thread before clearing gateway
state, so an active callback cannot write into the reset database."""

import json
import os
from threading import Event, Lock

import paho.mqtt.client as mqtt

from gateway.telemetry.service import ingest_environmental, ingest_pdu, ingest_smoke
from shared.devices import Protocol
from shared.telemetry import EnvironmentalTelemetry, PDUTelemetry, SmokeTelemetry

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_ROOT = "ot-soar/telemetry"
MQTT_READY_TIMEOUT_SECONDS = 5.0

_client: mqtt.Client | None = None
_client_lock = Lock()
_subscription_ready = Event()


def _on_connect(client, userdata, connect_flags, reason_code, properties):
    """Subscribe once the Paho v2 client reports a successful connection."""

    if not reason_code.is_failure:
        result, _ = client.subscribe(f"{MQTT_TOPIC_ROOT}/+")
        if result != mqtt.MQTT_ERR_SUCCESS:
            print("[gateway] MQTT subscription request failed " f"with code {result}")
        else:
            print(
                f"[gateway] MQTT connected; "
                f"subscription requested for {MQTT_TOPIC_ROOT}/+"
            )
    else:
        _subscription_ready.clear()
        print(f"[gateway] MQTT connection failed: {reason_code}")


def _on_subscribe(client, userdata, mid, reason_codes, properties):
    """Mark the MQTT subscriber ready only after the broker confirms SUBSCRIBE."""

    if reason_codes and any(code.is_failure for code in reason_codes):
        _subscription_ready.clear()
        print("[gateway] MQTT subscription was rejected: " f"{reason_codes}")
        return

    _subscription_ready.set()
    print(f"[gateway] MQTT subscribed to {MQTT_TOPIC_ROOT}/+")


def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    _subscription_ready.clear()

    if reason_code.is_failure:
        print("[gateway] MQTT subscriber disconnected unexpectedly: " f"{reason_code}")


def _on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))

        suffix = message.topic.rsplit("/", 1)[-1]

        if suffix == "environmental":
            ingest_environmental(EnvironmentalTelemetry(**payload), Protocol.MQTT)

        elif suffix == "smoke":
            ingest_smoke(SmokeTelemetry(**payload), Protocol.MQTT)

        elif suffix == "pdu":
            ingest_pdu(PDUTelemetry(**payload), Protocol.MQTT)

        else:
            print("[gateway] ignored unknown MQTT telemetry " f"topic {message.topic}")

    except Exception as exc:
        print("[gateway] MQTT telemetry rejected on " f"{message.topic}: {exc}")


def start_mqtt_ingestion(
    *,
    wait_until_ready: bool = False,
    timeout_seconds: float = MQTT_READY_TIMEOUT_SECONDS,
) -> None:
    """Start one MQTT subscriber.

    Normal application startup remains asynchronous.  Reset can request a
    readiness barrier so the facility is not restarted until the broker has
    acknowledged the gateway subscription.
    """

    global _client

    with _client_lock:
        existing = _client

        if existing is None:
            _subscription_ready.clear()

            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="ot-soar-gateway",
                clean_session=True,
            )

            client.on_connect = _on_connect
            client.on_subscribe = _on_subscribe
            client.on_disconnect = _on_disconnect
            client.on_message = _on_message

            client.reconnect_delay_set(min_delay=1, max_delay=10)

            client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)

            result = client.loop_start()
            if result != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(
                    "Could not start MQTT network loop: " f"error code {result}"
                )

            _client = client

    if wait_until_ready and not _subscription_ready.wait(timeout_seconds):
        stop_mqtt_ingestion()
        raise RuntimeError(
            "MQTT subscriber did not become ready within "
            f"{timeout_seconds:.1f} seconds"
        )


def stop_mqtt_ingestion() -> None:
    """Stop MQTT ingestion and wait until its callback thread has terminated.

    Paho's ``loop_stop()`` blocks until the network thread finishes.  Therefore,
    after this function returns, no pre-reset ``_on_message`` callback can still
    be mutating detector, telemetry, policy, or audit state.
    """

    global _client

    with _client_lock:
        client = _client
        _client = None
        _subscription_ready.clear()

    if client is None:
        return

    try:
        client.disconnect()
    finally:
        client.loop_stop()
