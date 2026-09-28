"""Restore seeded demo data after stopping telemetry publishers and ingestion."""

from gateway.database import get_connection
from gateway.infrastructure.devices.defaults import (
    reconcile_registered_device_protocols,
)
from gateway.integrations.mqtt import start_mqtt_ingestion, stop_mqtt_ingestion
from gateway.integrations.simulator import (
    quiesce_simulator_demo_state,
    rebuild_simulator_demo_state,
)
from gateway.iot_policy.engine import (
    clear_runtime_state as clear_iot_policy_runtime_state,
)
from gateway.iot_policy.repository import (
    migrate_iot_policy_ids_to_numeric,
    migrate_predefined_hvac_baseline_to_35,
    migrate_iot_policy_priorities_to_1_9,
    migrate_legacy_iot_policies,
    seed_predefined_iot_policies,
)
from gateway.personnel.seed import seed_personnel
from gateway.policy.defaults import seed_default_policies
from gateway.security.detector import detector
from gateway.security.repository import clear_security_event_cooldowns
from gateway.telemetry.store import clear_latest_telemetry
from gateway.seed import seed_database

DELETE_ORDER = [
    "personnel_room_access",
    "telemetry_history",
    "security_events",
    "response_events",
    "activity_events",
    "iot_device_policies",
    "iot_policy_seed_state",
    "abac_policy_seed_state",
    "policies",
    "personnel",
    "devices",
    "rooms",
]


def _table_exists(connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        is not None
    )


def reset_gateway_database_to_seed() -> None:
    """Delete persisted runtime/demo data and recreate only seeded records."""

    with get_connection() as connection:
        for table in DELETE_ORDER:
            if _table_exists(connection, table):
                connection.execute(f"DELETE FROM {table}")
        if _table_exists(connection, "sqlite_sequence"):
            connection.execute("DELETE FROM sqlite_sequence")

    detector.clear_all_runtime_state()
    clear_security_event_cooldowns()
    clear_iot_policy_runtime_state()
    clear_latest_telemetry()

    seed_database()
    reconcile_registered_device_protocols()
    seed_default_policies()
    migrate_legacy_iot_policies()
    seed_predefined_iot_policies()
    migrate_iot_policy_ids_to_numeric()
    migrate_predefined_hvac_baseline_to_35()
    migrate_iot_policy_priorities_to_1_9()
    seed_personnel()


async def reset_demo_to_seeded_state() -> dict:
    """Create a strict reset boundary around asynchronous MQTT telemetry.

    Reset order is important:

    1. stop facility publishers so no new telemetry is produced;
    2. stop the gateway MQTT network thread and wait for any active callback;
    3. clear/reseed persisted and in-memory gateway state;
    4. restart MQTT and wait for the broker to confirm the subscription;
    5. rebuild the facility so its first new telemetry belongs to the new run.

    This prevents pre-reset QoS 0 messages from accumulating in the gateway
    subscriber and being processed after the database/runtime reset.
    """

    quiesced = await quiesce_simulator_demo_state()

    # loop_stop() is a blocking join of Paho's network thread.  Once this
    # returns, an old _on_message callback cannot cross the reset boundary.
    stop_mqtt_ingestion()

    mqtt_restarted = False

    try:
        reset_gateway_database_to_seed()

        # Subscribe before facility publishers are recreated.  Waiting for
        # SUBACK avoids losing the first QoS 0 sample from a newly rebuilt
        # simulator because the gateway was not subscribed yet.
        start_mqtt_ingestion(wait_until_ready=True, timeout_seconds=5.0)
        mqtt_restarted = True

        simulator_result = await rebuild_simulator_demo_state()

    except Exception:
        # Avoid leaving the gateway permanently disconnected if reseeding fails
        # after the old subscriber has already been stopped.
        if not mqtt_restarted:
            try:
                start_mqtt_ingestion()
            except Exception:
                pass
        raise

    return {
        "status": "reset",
        "message": "Demo data reset to predefined seeded state.",
        "simulator_quiesce": quiesced,
        "simulator": simulator_result,
        "mqtt_reset_boundary": True,
    }
