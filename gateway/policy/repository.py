"""Read and write ABAC policies in SQLite.

The legacy subject_role column stores JSON role lists but still accepts old
single-role strings. New policies receive an abac-policy-NNN ID."""

import json
import re
import sqlite3

from gateway.database import get_connection
from shared.policy import Policy, PolicyCreate

GENERATED_POLICY_ID_PATTERN = re.compile(r"^abac-policy-(\d+)$")


def list_policies() -> list[Policy]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM policies ORDER BY priority DESC, policy_id"
        ).fetchall()
    return [_row_to_policy(row) for row in rows]


def get_policy(policy_id: str) -> Policy | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM policies WHERE policy_id = ?", (policy_id,)
        ).fetchone()
    return None if row is None else _row_to_policy(row)


def generate_next_policy_id() -> str:
    with get_connection() as connection:
        rows = connection.execute("SELECT policy_id FROM policies").fetchall()

    highest = 0
    for row in rows:
        match = GENERATED_POLICY_ID_PATTERN.match(row["policy_id"])
        if match:
            highest = max(highest, int(match.group(1)))

    return f"abac-policy-{highest + 1:03d}"


def create_policy(request: PolicyCreate) -> Policy:
    for _ in range(20):
        policy = Policy(policy_id=generate_next_policy_id(), **request.model_dump())
        if add_policy(policy):
            return policy

    raise RuntimeError("Could not allocate a unique ABAC policy ID")


def add_policy(policy: Policy) -> bool:
    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO policies (
                    policy_id,
                    name,
                    effect,
                    action,
                    subject_type,
                    resource_type,
                    subject_role,
                    minimum_clearance,
                    subject_device_type,
                    resource_device_type,
                    require_same_room,
                    allowed_subject_security_states,
                    allowed_resource_security_states,
                    start_hour,
                    end_hour,
                    priority,
                    enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _policy_values(policy),
            )
    except sqlite3.IntegrityError:
        return False

    return True


def update_policy(policy_id: str, policy: Policy) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE policies SET
                name = ?,
                effect = ?,
                action = ?,
                subject_type = ?,
                resource_type = ?,
                subject_role = ?,
                minimum_clearance = ?,
                subject_device_type = ?,
                resource_device_type = ?,
                require_same_room = ?,
                allowed_subject_security_states = ?,
                allowed_resource_security_states = ?,
                start_hour = ?,
                end_hour = ?,
                priority = ?,
                enabled = ?
            WHERE policy_id = ?
            """,
            (
                policy.name,
                policy.effect.value,
                policy.action.value,
                policy.subject_type.value,
                policy.resource_type.value,
                _roles_to_storage(policy.subject_roles),
                policy.minimum_clearance,
                (
                    policy.subject_device_type.value
                    if policy.subject_device_type
                    else None
                ),
                (
                    policy.resource_device_type.value
                    if policy.resource_device_type
                    else None
                ),
                int(policy.require_same_room),
                _security_states_to_json(policy.allowed_subject_security_states),
                _security_states_to_json(policy.allowed_resource_security_states),
                policy.start_hour,
                policy.end_hour,
                policy.priority,
                int(policy.enabled),
                policy_id,
            ),
        )

    return cursor.rowcount > 0


def delete_policy(policy_id: str) -> bool:
    """Delete one persisted ABAC policy by its stable identifier."""
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM policies WHERE policy_id = ?", (policy_id,)
        )
    return cursor.rowcount > 0


def policy_exists(policy_id: str) -> bool:
    return get_policy(policy_id) is not None


def _policy_values(policy: Policy):
    return (
        policy.policy_id,
        policy.name,
        policy.effect.value,
        policy.action.value,
        policy.subject_type.value,
        policy.resource_type.value,
        _roles_to_storage(policy.subject_roles),
        policy.minimum_clearance,
        policy.subject_device_type.value if policy.subject_device_type else None,
        policy.resource_device_type.value if policy.resource_device_type else None,
        int(policy.require_same_room),
        _security_states_to_json(policy.allowed_subject_security_states),
        _security_states_to_json(policy.allowed_resource_security_states),
        policy.start_hour,
        policy.end_hour,
        policy.priority,
        int(policy.enabled),
    )


def _roles_to_storage(roles: list[str] | None) -> str | None:
    if roles is None:
        return None
    return json.dumps(roles)


def _storage_to_roles(value: str | None) -> list[str] | None:
    if value is None:
        return None

    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [value]

    if isinstance(decoded, list):
        return [str(role) for role in decoded]

    if isinstance(decoded, str):
        return [decoded]

    return [value]


def _security_states_to_json(states):
    if states is None:
        return None
    return json.dumps([state.value for state in states])


def _json_to_security_states(value):
    return None if value is None else json.loads(value)


def _row_to_policy(row) -> Policy:
    return Policy(
        policy_id=row["policy_id"],
        name=row["name"],
        effect=row["effect"],
        action=row["action"],
        subject_type=row["subject_type"],
        resource_type=row["resource_type"],
        subject_roles=_storage_to_roles(row["subject_role"]),
        minimum_clearance=row["minimum_clearance"],
        subject_device_type=row["subject_device_type"],
        resource_device_type=row["resource_device_type"],
        require_same_room=bool(row["require_same_room"]),
        allowed_subject_security_states=_json_to_security_states(
            row["allowed_subject_security_states"]
        ),
        allowed_resource_security_states=_json_to_security_states(
            row["allowed_resource_security_states"]
        ),
        start_hour=row["start_hour"],
        end_hour=row["end_hour"],
        priority=row["priority"],
        enabled=bool(row["enabled"]),
    )
