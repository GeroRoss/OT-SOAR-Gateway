"""Seeded ABAC rules for the demo gateway."""

from gateway.database import get_connection
from gateway.policy.repository import add_policy, policy_exists, update_policy
from shared.devices import DeviceType, SecurityState
from shared.policy import Action, Policy, PolicyEffect, ResourceType, SubjectType

ACTIVE_DEVICE_STATES = [SecurityState.NORMAL, SecurityState.SUSPICIOUS]

ALL_PERSONNEL_ROLES = [
    "ot_administrator",
    "security_operator",
    "facility_engineer",
    "facility_operator",
    "technician",
    "contractor",
    "visitor",
]
ROLES_HVAC_PDU = ["facility_operator", "facility_engineer", "ot_administrator"]
ROLES_DOOR_OVERRIDE = ["security_operator", "facility_engineer", "ot_administrator"]
ROLES_INFRASTRUCTURE = [
    "technician",
    "facility_operator",
    "facility_engineer",
    "ot_administrator",
]
ROLES_PERSONNEL_ADMIN = ["facility_engineer", "ot_administrator"]
ROLES_IOT_POLICY_ADMIN = ["facility_engineer", "ot_administrator"]
ROLES_ABAC_ADMIN = ["ot_administrator"]
ROLES_SECURITY_RESET = ["security_operator", "facility_engineer", "ot_administrator"]


def _personnel_policy(
    policy_id,
    name,
    action,
    roles,
    clearance,
    resource_type,
    *,
    require_same_room=False,
    priority=5,
):
    return Policy(
        policy_id=policy_id,
        name=name,
        effect=PolicyEffect.ALLOW,
        action=action,
        subject_type=SubjectType.PERSONNEL,
        subject_roles=roles,
        minimum_clearance=clearance,
        resource_type=resource_type,
        require_same_room=require_same_room,
        priority=priority,
    )


DEFAULT_POLICIES = [
    Policy(
        policy_id="abac-policy-001",
        name="Environmental telemetry: own room",
        effect=PolicyEffect.ALLOW,
        action=Action.PUBLISH_ENVIRONMENTAL_TELEMETRY,
        subject_type=SubjectType.DEVICE,
        subject_device_type=DeviceType.ENVIRONMENTAL_SENSOR,
        resource_type=ResourceType.TELEMETRY,
        require_same_room=True,
        allowed_subject_security_states=ACTIVE_DEVICE_STATES,
        priority=5,
    ),
    Policy(
        policy_id="abac-policy-002",
        name="Smoke telemetry: own room",
        effect=PolicyEffect.ALLOW,
        action=Action.PUBLISH_SMOKE_TELEMETRY,
        subject_type=SubjectType.DEVICE,
        subject_device_type=DeviceType.SMOKE_SENSOR,
        resource_type=ResourceType.TELEMETRY,
        require_same_room=True,
        allowed_subject_security_states=ACTIVE_DEVICE_STATES,
        priority=5,
    ),
    Policy(
        policy_id="abac-policy-003",
        name="PDU telemetry: own room",
        effect=PolicyEffect.ALLOW,
        action=Action.PUBLISH_PDU_TELEMETRY,
        subject_type=SubjectType.DEVICE,
        subject_device_type=DeviceType.PDU,
        resource_type=ResourceType.TELEMETRY,
        require_same_room=True,
        allowed_subject_security_states=ACTIVE_DEVICE_STATES,
        priority=5,
    ),
    Policy(
        policy_id="abac-policy-004",
        name="Staff control: HVAC",
        effect=PolicyEffect.ALLOW,
        action=Action.CONTROL_HVAC,
        subject_type=SubjectType.PERSONNEL,
        subject_roles=ROLES_HVAC_PDU,
        minimum_clearance=2,
        resource_type=ResourceType.DEVICE,
        resource_device_type=DeviceType.HVAC,
        allowed_resource_security_states=ACTIVE_DEVICE_STATES,
        priority=5,
    ),
    Policy(
        policy_id="abac-policy-005",
        name="Staff control: PDU",
        effect=PolicyEffect.ALLOW,
        action=Action.CONTROL_PDU,
        subject_type=SubjectType.PERSONNEL,
        subject_roles=ROLES_HVAC_PDU,
        minimum_clearance=2,
        resource_type=ResourceType.DEVICE,
        resource_device_type=DeviceType.PDU,
        allowed_resource_security_states=ACTIVE_DEVICE_STATES,
        priority=5,
    ),
    Policy(
        policy_id="abac-policy-006",
        name="Privileged door override",
        effect=PolicyEffect.ALLOW,
        action=Action.CONTROL_DOOR,
        subject_type=SubjectType.PERSONNEL,
        subject_roles=ROLES_DOOR_OVERRIDE,
        minimum_clearance=4,
        resource_type=ResourceType.DEVICE,
        resource_device_type=DeviceType.BIOMETRIC_DOOR,
        allowed_resource_security_states=ACTIVE_DEVICE_STATES,
        priority=6,
    ),
    Policy(
        policy_id="abac-policy-007",
        name="Authorized biometric door access",
        effect=PolicyEffect.ALLOW,
        action=Action.REQUEST_DOOR_ACCESS,
        subject_type=SubjectType.PERSONNEL,
        subject_roles=ALL_PERSONNEL_ROLES,
        resource_type=ResourceType.DEVICE,
        resource_device_type=DeviceType.BIOMETRIC_DOOR,
        allowed_resource_security_states=ACTIVE_DEVICE_STATES,
        priority=4,
    ),
    _personnel_policy(
        "abac-policy-008",
        "Infrastructure staff may create rooms",
        Action.CREATE_ROOM,
        ROLES_INFRASTRUCTURE,
        3,
        ResourceType.ROOM,
    ),
    _personnel_policy(
        "abac-policy-009",
        "Infrastructure staff may edit rooms",
        Action.EDIT_ROOM,
        ROLES_INFRASTRUCTURE,
        3,
        ResourceType.ROOM,
    ),
    _personnel_policy(
        "abac-policy-022",
        "Infrastructure staff may delete empty unreferenced rooms",
        Action.DELETE_ROOM,
        ROLES_INFRASTRUCTURE,
        3,
        ResourceType.ROOM,
    ),
    _personnel_policy(
        "abac-policy-010",
        "Infrastructure staff may register devices",
        Action.REGISTER_DEVICE,
        ROLES_INFRASTRUCTURE,
        3,
        ResourceType.DEVICE,
        require_same_room=True,
    ),
    _personnel_policy(
        "abac-policy-011",
        "Infrastructure staff may edit devices",
        Action.EDIT_DEVICE,
        ROLES_INFRASTRUCTURE,
        3,
        ResourceType.DEVICE,
        require_same_room=True,
    ),
    _personnel_policy(
        "abac-policy-012",
        "Infrastructure staff may delete devices",
        Action.DELETE_DEVICE,
        ROLES_INFRASTRUCTURE,
        3,
        ResourceType.DEVICE,
        require_same_room=True,
    ),
    _personnel_policy(
        "abac-policy-013",
        "Personnel administrators may add personnel",
        Action.CREATE_PERSONNEL,
        ROLES_PERSONNEL_ADMIN,
        4,
        ResourceType.PERSONNEL,
    ),
    _personnel_policy(
        "abac-policy-014",
        "Personnel administrators may edit personnel",
        Action.EDIT_PERSONNEL,
        ROLES_PERSONNEL_ADMIN,
        4,
        ResourceType.PERSONNEL,
    ),
    _personnel_policy(
        "abac-policy-015",
        "Engineering administrators may create IoT policies",
        Action.CREATE_IOT_POLICY,
        ROLES_IOT_POLICY_ADMIN,
        4,
        ResourceType.IOT_POLICY,
    ),
    _personnel_policy(
        "abac-policy-016",
        "Engineering administrators may edit IoT policies",
        Action.EDIT_IOT_POLICY,
        ROLES_IOT_POLICY_ADMIN,
        4,
        ResourceType.IOT_POLICY,
    ),
    _personnel_policy(
        "abac-policy-017",
        "Engineering administrators may delete IoT policies",
        Action.DELETE_IOT_POLICY,
        ROLES_IOT_POLICY_ADMIN,
        4,
        ResourceType.IOT_POLICY,
    ),
    _personnel_policy(
        "abac-policy-018",
        "OT administrators may create ABAC policies",
        Action.CREATE_ABAC_POLICY,
        ROLES_ABAC_ADMIN,
        5,
        ResourceType.ABAC_POLICY,
        priority=7,
    ),
    _personnel_policy(
        "abac-policy-019",
        "OT administrators may edit ABAC policies",
        Action.EDIT_ABAC_POLICY,
        ROLES_ABAC_ADMIN,
        5,
        ResourceType.ABAC_POLICY,
        priority=7,
    ),
    _personnel_policy(
        "abac-policy-020",
        "OT administrators may delete ABAC policies",
        Action.DELETE_ABAC_POLICY,
        ROLES_ABAC_ADMIN,
        5,
        ResourceType.ABAC_POLICY,
        priority=7,
    ),
    _personnel_policy(
        "abac-policy-021",
        "Privileged staff may reset quarantined device security state",
        Action.RESET_SECURITY_STATE,
        ROLES_SECURITY_RESET,
        4,
        ResourceType.DEVICE,
        require_same_room=True,
        priority=6,
    ),
]


ABAC_SEED_VERSION = 3
ABAC_SEED_KEY = "default-abac-policies"


def seed_default_policies():
    """Reconcile predefined ABAC policies once per baseline version.

    A versioned seed marker lets migrations repair older persisted built-ins once,
    while preserving later operator edits or deletions across ordinary restarts.
    Explicit demo reset clears the marker and restores the complete baseline.
    """
    with get_connection() as connection:
        row = connection.execute(
            "SELECT version FROM abac_policy_seed_state WHERE seed_key = ?",
            (ABAC_SEED_KEY,),
        ).fetchone()
        current_version = row["version"] if row else 0

    if current_version >= ABAC_SEED_VERSION:
        print("[gateway] predefined ABAC policy baseline already migrated")
        return

    for policy in DEFAULT_POLICIES:
        if policy_exists(policy.policy_id):
            update_policy(policy.policy_id, policy)
        else:
            add_policy(policy)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO abac_policy_seed_state (seed_key, version)
            VALUES (?, ?)
            ON CONFLICT(seed_key) DO UPDATE SET version = excluded.version
            """,
            (ABAC_SEED_KEY, ABAC_SEED_VERSION),
        )

    print(
        f"[gateway] predefined ABAC policies migrated to baseline v{ABAC_SEED_VERSION}"
    )
