"""Demo accounts covering the roles used in access-control evaluation.

The administrator is seeded first to make the initial dashboard session
convenient for development."""

from gateway.personnel.repository import add_personnel, get_personnel
from shared.personnel import Personnel, PersonnelRole

DEMO_PERSONNEL = [
    Personnel(
        person_id="personnel-001",
        name="John Smith",
        role=PersonnelRole.OT_ADMINISTRATOR,
        clearance=5,
        authorized_rooms=["room-001", "room-002"],
        active=True,
    ),
    Personnel(
        person_id="personnel-002",
        name="Michael Brown",
        role=PersonnelRole.FACILITY_ENGINEER,
        clearance=4,
        authorized_rooms=["room-001", "room-002"],
        active=True,
    ),
    Personnel(
        person_id="personnel-003",
        name="Sarah Chen",
        role=PersonnelRole.SECURITY_OPERATOR,
        clearance=4,
        authorized_rooms=["room-001", "room-002"],
        active=True,
    ),
    Personnel(
        person_id="personnel-004",
        name="Olivia Wilson",
        role=PersonnelRole.FACILITY_OPERATOR,
        clearance=2,
        authorized_rooms=["room-001", "room-002"],
        active=True,
    ),
    Personnel(
        person_id="personnel-005",
        name="Noah Lee",
        role=PersonnelRole.TECHNICIAN,
        clearance=2,
        authorized_rooms=["room-001", "room-002"],
        active=True,
    ),
    Personnel(
        person_id="personnel-006",
        name="Emily Davis",
        role=PersonnelRole.CONTRACTOR,
        clearance=1,
        authorized_rooms=["room-001"],
        active=True,
    ),
    Personnel(
        person_id="personnel-007",
        name="Lucifer Morningstar",
        role=PersonnelRole.VISITOR,
        clearance=0,
        authorized_rooms=[],
        active=True,
    ),
]


def seed_personnel():
    """Insert missing demonstration personnel in deterministic ID order."""

    for personnel in DEMO_PERSONNEL:
        if get_personnel(personnel.person_id) is None:
            add_personnel(personnel)

    print("[gateway] demonstration personnel available")
