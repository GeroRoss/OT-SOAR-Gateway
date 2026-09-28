"""Publish simulator readings using each registered device's transport."""

import asyncio
import json
import os
import time
from threading import Lock

import httpx
import paho.mqtt.client as mqtt

from shared.devices import Device, Protocol

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_ROOT = "ot-soar/telemetry"


class MQTTTelemetryPublisher:
    """Maintains one MQTT connection for simulated MQTT telemetry."""

    def __init__(self):
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="facility-simulator"
        )

        self.connected = False
        self.started = False
        self.lock = Lock()
        self.generation_lock = Lock()
        self.generation = 0
        self.enabled = True

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        self.client.reconnect_delay_set(min_delay=1, max_delay=10)

    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        self.connected = not reason_code.is_failure

        if self.connected:
            print("[facility] MQTT telemetry publisher connected")
        else:
            print(
                "[facility] MQTT telemetry publisher connection "
                f"failed: {reason_code}"
            )

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties
    ):
        self.connected = False

        if reason_code.is_failure:
            print(
                "[facility] MQTT telemetry publisher disconnected "
                f"unexpectedly: {reason_code}"
            )

    def _ensure_connected(self):
        with self.lock:
            if self.connected:
                return

            if not self.started:
                self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
                self.client.loop_start()
                self.started = True

            # The connection callback runs on the MQTT network thread.
            # Give it a short bounded period to complete before publishing.
            deadline = time.monotonic() + 5.0

            while not self.connected:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "MQTT broker connection was not ready " "within 5 seconds"
                    )
                time.sleep(0.05)

    def capture_generation(self) -> int | None:
        """Return the active telemetry generation, or None while reset is quiesced."""

        with self.generation_lock:
            if not self.enabled:
                return None
            return self.generation

    def begin_reset(self) -> int:
        """Invalidate all already-scheduled MQTT publishes and pause new ones."""

        with self.generation_lock:
            self.generation += 1
            self.enabled = False
            return self.generation

    def end_reset(self) -> int:
        """Allow MQTT publishing again for the current simulator generation."""

        with self.generation_lock:
            self.enabled = True
            return self.generation

    def publish(self, telemetry_type: str, payload: dict, expected_generation: int):
        # Hold the generation lock for the complete publish. A reset therefore
        # cannot advance the generation until an in-flight publish has either
        # completed or failed, and queued publishes from the old generation
        # are discarded when they eventually run.
        with self.generation_lock:
            if not self.enabled or expected_generation != self.generation:
                return

            self._ensure_connected()

            result = self.client.publish(
                f"{MQTT_TOPIC_ROOT}/{telemetry_type}", json.dumps(payload), qos=0
            )

            result.wait_for_publish(timeout=3)

            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT publish failed with code {result.rc}")


mqtt_publisher = MQTTTelemetryPublisher()


def begin_telemetry_reset() -> int:
    """Pause MQTT telemetry and invalidate work queued by the old simulator."""

    return mqtt_publisher.begin_reset()


def end_telemetry_reset() -> int:
    """Resume MQTT telemetry for the newly rebuilt simulator."""

    return mqtt_publisher.end_reset()


async def send_device_telemetry(
    device: Device, telemetry_type: str, payload: dict, gateway_url: str
) -> None:
    if device.protocol == Protocol.MQTT:
        generation = mqtt_publisher.capture_generation()
        if generation is None:
            return

        await asyncio.to_thread(
            mqtt_publisher.publish, telemetry_type, payload, generation
        )
        return

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{gateway_url}/telemetry/{telemetry_type}", json=payload
        )
        response.raise_for_status()
