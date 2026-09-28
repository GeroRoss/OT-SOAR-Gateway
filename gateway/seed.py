"""Default rooms and devices for a fresh database or demo reset."""

from gateway.registry import add_device, add_room, registry_is_empty

from shared.devices import Criticality, Device, DeviceType, Protocol
from shared.rooms import Room


def seed_database():
    """
    Populate a completely fresh registry with three fully equipped
    demonstration server rooms.

    Existing persistent room/device registrations are not changed.
    """

    if not registry_is_empty():
        return

    demo_rooms = [
        Room(room_id="room-001", name="Server Room 1"),
        Room(room_id="room-002", name="Server Room 2"),
    ]

    for room in demo_rooms:
        add_room(room)

    demo_devices = [
        # --------------------------------------------------------------
        # Environmental sensors
        # --------------------------------------------------------------
        Device(
            device_id="env-001",
            name="Environmental Sensor 1-1",
            device_type=DeviceType.ENVIRONMENTAL_SENSOR,
            room_id="room-001",
            protocol=Protocol.MQTT,
            criticality=Criticality.MEDIUM,
        ),
        Device(
            device_id="env-002",
            name="Environmental Sensor 1-2",
            device_type=DeviceType.ENVIRONMENTAL_SENSOR,
            room_id="room-001",
            protocol=Protocol.MQTT,
            criticality=Criticality.MEDIUM,
        ),
        Device(
            device_id="env-003",
            name="Environmental Sensor 1-3",
            device_type=DeviceType.ENVIRONMENTAL_SENSOR,
            room_id="room-001",
            protocol=Protocol.MQTT,
            criticality=Criticality.MEDIUM,
        ),
        # Two additional independent logical environmental endpoints per
        # room provide the minimum three-source redundancy needed for
        # cross-sensor plausibility checks. They observe the same simulated
        # physical room but retain separate identity, telemetry and security
        # state at the gateway.
        Device(
            device_id="env-004",
            name="Environmental Sensor 2-1",
            device_type=DeviceType.ENVIRONMENTAL_SENSOR,
            room_id="room-002",
            protocol=Protocol.MQTT,
            criticality=Criticality.MEDIUM,
        ),
        Device(
            device_id="env-005",
            name="Environmental Sensor 2-2",
            device_type=DeviceType.ENVIRONMENTAL_SENSOR,
            room_id="room-002",
            protocol=Protocol.MQTT,
            criticality=Criticality.MEDIUM,
        ),
        Device(
            device_id="env-006",
            name="Environmental Sensor 2-3",
            device_type=DeviceType.ENVIRONMENTAL_SENSOR,
            room_id="room-002",
            protocol=Protocol.MQTT,
            criticality=Criticality.MEDIUM,
        ),
        # --------------------------------------------------------------
        # Smoke sensors
        # --------------------------------------------------------------
        Device(
            device_id="smoke-001",
            name="Smoke Sensor 1-1",
            device_type=DeviceType.SMOKE_SENSOR,
            room_id="room-001",
            protocol=Protocol.MQTT,
            criticality=Criticality.SAFETY_CRITICAL,
        ),
        Device(
            device_id="smoke-002",
            name="Smoke Sensor 1-2",
            device_type=DeviceType.SMOKE_SENSOR,
            room_id="room-001",
            protocol=Protocol.MQTT,
            criticality=Criticality.SAFETY_CRITICAL,
        ),
        Device(
            device_id="smoke-003",
            name="Smoke Sensor 2-1",
            device_type=DeviceType.SMOKE_SENSOR,
            room_id="room-002",
            protocol=Protocol.MQTT,
            criticality=Criticality.SAFETY_CRITICAL,
        ),
        Device(
            device_id="smoke-004",
            name="Smoke Sensor 2-2",
            device_type=DeviceType.SMOKE_SENSOR,
            room_id="room-002",
            protocol=Protocol.MQTT,
            criticality=Criticality.SAFETY_CRITICAL,
        ),
        # --------------------------------------------------------------
        # Smart PDUs
        # --------------------------------------------------------------
        Device(
            device_id="pdu-001",
            name="Smart PDU 1",
            device_type=DeviceType.PDU,
            room_id="room-001",
            protocol=Protocol.HTTP,
            criticality=Criticality.SAFETY_CRITICAL,
        ),
        Device(
            device_id="pdu-002",
            name="Smart PDU 2",
            device_type=DeviceType.PDU,
            room_id="room-002",
            protocol=Protocol.HTTP,
            criticality=Criticality.SAFETY_CRITICAL,
        ),
        # --------------------------------------------------------------
        # HVAC controllers
        # --------------------------------------------------------------
        Device(
            device_id="hvac-001",
            name="HVAC Controller 1",
            device_type=DeviceType.HVAC,
            room_id="room-001",
            protocol=Protocol.HTTP,
            criticality=Criticality.SAFETY_CRITICAL,
        ),
        Device(
            device_id="hvac-002",
            name="HVAC Controller 2",
            device_type=DeviceType.HVAC,
            room_id="room-002",
            protocol=Protocol.HTTP,
            criticality=Criticality.SAFETY_CRITICAL,
        ),
        # --------------------------------------------------------------
        # Biometric doors
        # --------------------------------------------------------------
        Device(
            device_id="door-001",
            name="Biometric Door 1",
            device_type=DeviceType.BIOMETRIC_DOOR,
            room_id="room-001",
            protocol=Protocol.HTTP,
            criticality=Criticality.HIGH,
        ),
        Device(
            device_id="door-002",
            name="Biometric Door 2",
            device_type=DeviceType.BIOMETRIC_DOOR,
            room_id="room-002",
            protocol=Protocol.HTTP,
            criticality=Criticality.HIGH,
        ),
    ]

    for device in demo_devices:
        add_device(device)

    print(
        "[gateway] fresh registry seeded with " "2 rooms and 16 demonstration devices"
    )
