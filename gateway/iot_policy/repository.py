"""Store automation policies and migrate the seeded defaults."""

import json
import re

from gateway.database import get_connection
from gateway.iot_policy.models import IoTDevicePolicy, IoTDevicePolicyCreate

POLICY_TYPE = "orchestration_rule"
LEGACY_POLICY_ID = "environmental-hvac-automation"
SEED_MARKER = "predefined_iot_policies_v2"
NUMERIC_ID_MIGRATION_MARKER = "numeric_iot_policy_ids_v1"
PRIORITY_SCALE_MIGRATION_MARKER = "iot_policy_priority_scale_1_to_9_v1"
HVAC_BASELINE_MIGRATION_MARKER = "iot_policy_hvac_baseline_35_v1"


PREDEFINED_POLICIES = [
    # Temperature stages: progressively stronger cooling as server-room heat rises.
    dict(
        policy_id="iot-policy-001",
        name="Temperature stage 1",
        enabled=True,
        trigger_device_type="environmental_sensor",
        trigger_attribute="temperature",
        operator="greater_than_or_equal",
        threshold=25,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=35,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-002",
        name="Temperature stage 2",
        enabled=True,
        trigger_device_type="environmental_sensor",
        trigger_attribute="temperature",
        operator="greater_than_or_equal",
        threshold=30,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=50,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-003",
        name="Temperature stage 3",
        enabled=True,
        trigger_device_type="environmental_sensor",
        trigger_attribute="temperature",
        operator="greater_than_or_equal",
        threshold=40,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=70,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-004",
        name="Temperature stage 4",
        enabled=True,
        trigger_device_type="environmental_sensor",
        trigger_attribute="temperature",
        operator="greater_than_or_equal",
        threshold=50,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=85,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-005",
        name="Temperature emergency cooling",
        enabled=True,
        trigger_device_type="environmental_sensor",
        trigger_attribute="temperature",
        operator="greater_than_or_equal",
        threshold=60,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=100,
        fallback_value=35,
        priority=1,
    ),
    # Humidity stages. Humidity itself remains stable unless changed by the simulator.
    dict(
        policy_id="iot-policy-006",
        name="Humidity stage 1",
        enabled=True,
        trigger_device_type="environmental_sensor",
        trigger_attribute="humidity",
        operator="greater_than_or_equal",
        threshold=60,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=40,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-007",
        name="Humidity stage 2",
        enabled=True,
        trigger_device_type="environmental_sensor",
        trigger_attribute="humidity",
        operator="greater_than_or_equal",
        threshold=75,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=65,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-008",
        name="Humidity emergency extraction",
        enabled=True,
        trigger_device_type="environmental_sensor",
        trigger_attribute="humidity",
        operator="greater_than_or_equal",
        threshold=90,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=90,
        fallback_value=35,
        priority=1,
    ),
    # Smoke response. These model simplified extraction / emergency actions in the PoC.
    dict(
        policy_id="iot-policy-009",
        name="Smoke extraction stage 1",
        enabled=True,
        trigger_device_type="smoke_sensor",
        trigger_attribute="smoke_level",
        operator="greater_than_or_equal",
        threshold=1,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=50,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-010",
        name="Smoke extraction stage 2",
        enabled=True,
        trigger_device_type="smoke_sensor",
        trigger_attribute="smoke_level",
        operator="greater_than_or_equal",
        threshold=10,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=75,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-011",
        name="Smoke emergency extraction",
        enabled=True,
        trigger_device_type="smoke_sensor",
        trigger_attribute="smoke_level",
        operator="greater_than_or_equal",
        threshold=25,
        required_source_state="normal",
        target_device_type="hvac",
        target_scope="same_room",
        action="set_cooling",
        action_value=100,
        fallback_value=35,
        priority=1,
    ),
    dict(
        policy_id="iot-policy-012",
        name="Smoke emergency: room PDU off",
        enabled=True,
        trigger_device_type="smoke_sensor",
        trigger_attribute="smoke_level",
        operator="greater_than_or_equal",
        threshold=25,
        required_source_state="normal",
        target_device_type="pdu",
        target_scope="same_room",
        action="set_power",
        action_value=0,
        fallback_value=None,
        priority=6,
    ),
    dict(
        policy_id="iot-policy-013",
        name="Smoke emergency: room door unlock",
        enabled=True,
        trigger_device_type="smoke_sensor",
        trigger_attribute="smoke_level",
        operator="greater_than_or_equal",
        threshold=25,
        required_source_state="normal",
        target_device_type="biometric_door",
        target_scope="same_room",
        action="set_locked",
        action_value=0,
        fallback_value=None,
        priority=6,
    ),
    # Demonstrates facility-wide orchestration, but stays disabled because it is disruptive.
    dict(
        policy_id="iot-policy-014",
        name="Severe smoke: all PDUs off",
        enabled=True,
        trigger_device_type="smoke_sensor",
        trigger_attribute="smoke_level",
        operator="greater_than_or_equal",
        threshold=70,
        required_source_state="normal",
        target_device_type="pdu",
        target_scope="whole_facility",
        action="set_power",
        action_value=0,
        fallback_value=None,
        priority=9,
    ),
]


def migrate_legacy_iot_policies() -> None:
    """Remove the previous built-in HVAC controller without touching user rules."""

    with get_connection() as connection:
        connection.execute(
            "DELETE FROM iot_device_policies WHERE policy_id = ?", (LEGACY_POLICY_ID,)
        )


def seed_predefined_iot_policies() -> None:
    """Install the demonstration rule set once, preserving later user edits/deletes."""

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS iot_policy_seed_state (
                seed_key TEXT PRIMARY KEY,
                applied INTEGER NOT NULL
            )
            """)
        already_seeded = connection.execute(
            "SELECT 1 FROM iot_policy_seed_state WHERE seed_key = ?", (SEED_MARKER,)
        ).fetchone()
        if already_seeded:
            return

        for data in PREDEFINED_POLICIES:
            policy = IoTDevicePolicy(**data)
            connection.execute(
                """
                INSERT OR IGNORE INTO iot_device_policies (
                    policy_id, name, policy_type, enabled, config_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    policy.policy_id,
                    policy.name,
                    POLICY_TYPE,
                    int(policy.enabled),
                    json.dumps(_policy_config(policy)),
                ),
            )

        connection.execute(
            "INSERT OR REPLACE INTO iot_policy_seed_state (seed_key, applied) VALUES (?, 1)",
            (SEED_MARKER,),
        )


def migrate_predefined_hvac_baseline_to_35() -> None:
    """Move the seeded HVAC fallback from 20% to the new 35% normal baseline.

    Existing Docker volumes may already contain the earlier predefined policies,
    so changing ``PREDEFINED_POLICIES`` alone would not update them.  This
    one-time migration only touches the reserved predefined cooling-policy IDs
    and only when their persisted fallback is still the old 20% value.
    """

    predefined_cooling_ids = {
        policy["policy_id"]
        for policy in PREDEFINED_POLICIES
        if policy.get("action") == "set_cooling"
    }

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS iot_policy_seed_state (
                seed_key TEXT PRIMARY KEY,
                applied INTEGER NOT NULL
            )
            """)
        already_applied = connection.execute(
            "SELECT 1 FROM iot_policy_seed_state WHERE seed_key = ?",
            (HVAC_BASELINE_MIGRATION_MARKER,),
        ).fetchone()
        if already_applied:
            return

        rows = connection.execute(
            """
            SELECT policy_id, config_json
            FROM iot_device_policies
            WHERE policy_type = ?
            """,
            (POLICY_TYPE,),
        ).fetchall()

        for row in rows:
            if row["policy_id"] not in predefined_cooling_ids:
                continue
            config = json.loads(row["config_json"])
            if config.get("action") != "set_cooling":
                continue
            if config.get("fallback_value") != 20:
                continue
            config["fallback_value"] = 35
            connection.execute(
                "UPDATE iot_device_policies SET config_json = ? WHERE policy_id = ?",
                (json.dumps(config), row["policy_id"]),
            )

        connection.execute(
            "INSERT OR REPLACE INTO iot_policy_seed_state (seed_key, applied) VALUES (?, 1)",
            (HVAC_BASELINE_MIGRATION_MARKER,),
        )


def migrate_iot_policy_ids_to_numeric() -> None:
    """Renumber every orchestration policy once as iot-policy-00x.

    Existing SQLite volumes may contain earlier descriptive IDs such as
    ``iot-default-temp-25``.  The migration uses temporary IDs first so
    existing numeric IDs cannot collide while rows are being renumbered.
    Row insertion order is preserved, so predefined rules remain first and
    subsequently created user rules keep their relative order.
    """

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS iot_policy_seed_state (
                seed_key TEXT PRIMARY KEY,
                applied INTEGER NOT NULL
            )
            """)
        already_applied = connection.execute(
            "SELECT 1 FROM iot_policy_seed_state WHERE seed_key = ?",
            (NUMERIC_ID_MIGRATION_MARKER,),
        ).fetchone()
        if already_applied:
            return

        rows = connection.execute(
            """
            SELECT rowid, policy_id
            FROM iot_device_policies
            WHERE policy_type = ?
            ORDER BY rowid
            """,
            (POLICY_TYPE,),
        ).fetchall()

        # Two-phase rename prevents primary-key collisions when a database
        # already contains both old descriptive IDs and newer numeric IDs.
        for row in rows:
            connection.execute(
                "UPDATE iot_device_policies SET policy_id = ? WHERE rowid = ?",
                (f"__iot-policy-migration-{row['rowid']}", row["rowid"]),
            )

        for index, row in enumerate(rows, start=1):
            connection.execute(
                "UPDATE iot_device_policies SET policy_id = ? WHERE rowid = ?",
                (f"iot-policy-{index:03d}", row["rowid"]),
            )

        connection.execute(
            "INSERT OR REPLACE INTO iot_policy_seed_state (seed_key, applied) VALUES (?, 1)",
            (NUMERIC_ID_MIGRATION_MARKER,),
        )


def migrate_iot_policy_priorities_to_1_9() -> None:
    """Migrate persisted orchestration priorities onto the 1-9 scale once.

    HVAC rules do not use numerical priority, so they are normalized to 1.
    Discrete actuator rules are ranked per target/action with same-room rules
    first and whole-facility rules last, preserving their previous ordering.
    This keeps facility-wide rules above local rules while producing unique
    priorities suitable for the simplified PoC scale.
    """

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS iot_policy_seed_state (
                seed_key TEXT PRIMARY KEY,
                applied INTEGER NOT NULL
            )
            """)
        already_applied = connection.execute(
            "SELECT 1 FROM iot_policy_seed_state WHERE seed_key = ?",
            (PRIORITY_SCALE_MIGRATION_MARKER,),
        ).fetchone()
        if already_applied:
            return

        rows = connection.execute(
            """
            SELECT rowid, policy_id, config_json
            FROM iot_device_policies
            WHERE policy_type = ?
            ORDER BY rowid
            """,
            (POLICY_TYPE,),
        ).fetchall()

        parsed = []
        for row in rows:
            config = json.loads(row["config_json"])
            parsed.append({"row": row, "config": config})

        # Fresh/current seed data is already on the 1-9 scale; preserve the
        # deliberately chosen priorities (for example local PDU=6, facility=9).
        if all(1 <= int(item["config"].get("priority", 0)) <= 9 for item in parsed):
            connection.execute(
                "INSERT OR REPLACE INTO iot_policy_seed_state (seed_key, applied) VALUES (?, 1)",
                (PRIORITY_SCALE_MIGRATION_MARKER,),
            )
            return

        # Cooling is resolved by maximum requested output, not by priority.
        for item in parsed:
            if item["config"].get("action") == "set_cooling":
                item["config"]["priority"] = 1

        groups = {}
        for item in parsed:
            config = item["config"]
            if config.get("action") == "set_cooling":
                continue
            key = (config.get("target_device_type"), config.get("action"))
            groups.setdefault(key, []).append(item)

        for key, items in groups.items():
            if len(items) > 9:
                raise RuntimeError(
                    f"Cannot migrate {len(items)} policies for {key[0]}.{key[1]} "
                    "onto unique priorities 1-9. Reset demo data or remove rules first."
                )
            items.sort(
                key=lambda item: (
                    item["config"].get("target_scope") == "whole_facility",
                    int(item["config"].get("priority", 0)),
                    item["row"]["policy_id"],
                )
            )
            for rank, item in enumerate(items, start=1):
                item["config"]["priority"] = rank

        for item in parsed:
            connection.execute(
                "UPDATE iot_device_policies SET config_json = ? WHERE rowid = ?",
                (json.dumps(item["config"]), item["row"]["rowid"]),
            )

        connection.execute(
            "INSERT OR REPLACE INTO iot_policy_seed_state (seed_key, applied) VALUES (?, 1)",
            (PRIORITY_SCALE_MIGRATION_MARKER,),
        )


def generate_next_iot_policy_id() -> str:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT policy_id FROM iot_device_policies"
        ).fetchall()
    highest = 0
    pattern = re.compile(r"^iot-policy-(\d+)$")
    for row in rows:
        match = pattern.match(row["policy_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"iot-policy-{highest + 1:03d}"


def list_iot_device_policies() -> list[IoTDevicePolicy]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM iot_device_policies ORDER BY policy_id"
        ).fetchall()
    return [_row_to_policy(row) for row in rows if row["policy_type"] == POLICY_TYPE]


def get_iot_device_policy(policy_id: str) -> IoTDevicePolicy | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM iot_device_policies WHERE policy_id = ?", (policy_id,)
        ).fetchone()
    if row is None or row["policy_type"] != POLICY_TYPE:
        return None
    return _row_to_policy(row)


def create_iot_device_policy(request: IoTDevicePolicyCreate) -> IoTDevicePolicy:
    policy = IoTDevicePolicy(
        policy_id=generate_next_iot_policy_id(), **request.model_dump()
    )
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO iot_device_policies (
                policy_id, name, policy_type, enabled, config_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                policy.policy_id,
                policy.name,
                POLICY_TYPE,
                int(policy.enabled),
                json.dumps(_policy_config(policy)),
            ),
        )
    return policy


def update_iot_device_policy(policy: IoTDevicePolicy) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE iot_device_policies
            SET name = ?, enabled = ?, policy_type = ?, config_json = ?
            WHERE policy_id = ?
            """,
            (
                policy.name,
                int(policy.enabled),
                POLICY_TYPE,
                json.dumps(_policy_config(policy)),
                policy.policy_id,
            ),
        )
    return cursor.rowcount > 0


def delete_iot_device_policy(policy_id: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM iot_device_policies WHERE policy_id = ? AND policy_type = ?",
            (policy_id, POLICY_TYPE),
        )
    return cursor.rowcount > 0


def _policy_config(policy: IoTDevicePolicy) -> dict:
    data = policy.model_dump(mode="json")
    data.pop("policy_id", None)
    data.pop("name", None)
    data.pop("enabled", None)
    return data


def _row_to_policy(row) -> IoTDevicePolicy:
    config = json.loads(row["config_json"])
    return IoTDevicePolicy(
        policy_id=row["policy_id"],
        name=row["name"],
        enabled=bool(row["enabled"]),
        **config,
    )
