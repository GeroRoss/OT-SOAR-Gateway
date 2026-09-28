"""Protocol and criticality defaults assigned by the device registry."""

from gateway.database import get_connection
from shared.devices import Criticality, DeviceType, Protocol

DEVICE_DEFAULTS = {
    DeviceType.ENVIRONMENTAL_SENSOR: {
        "protocol": Protocol.MQTT,
        "criticality": Criticality.MEDIUM,
    },
    DeviceType.SMOKE_SENSOR: {
        "protocol": Protocol.MQTT,
        "criticality": Criticality.SAFETY_CRITICAL,
    },
    DeviceType.PDU: {
        "protocol": Protocol.HTTP,
        "criticality": Criticality.SAFETY_CRITICAL,
    },
    DeviceType.HVAC: {
        "protocol": Protocol.HTTP,
        "criticality": Criticality.SAFETY_CRITICAL,
    },
    DeviceType.BIOMETRIC_DOOR: {
        "protocol": Protocol.HTTP,
        "criticality": Criticality.HIGH,
    },
}


def reconcile_registered_device_protocols() -> None:
    """Apply type-owned transport defaults to existing persisted registrations.

    Protocol is intentionally not operator-editable in this PoC.  Existing demo
    databases created before MQTT support therefore need a one-time reconciliation
    so environmental and smoke sensors actually use MQTT after an upgrade.
    """

    with get_connection() as connection:
        for device_type, defaults in DEVICE_DEFAULTS.items():
            connection.execute(
                "UPDATE devices SET protocol = ? WHERE device_type = ? AND protocol != ?",
                (
                    defaults["protocol"].value,
                    device_type.value,
                    defaults["protocol"].value,
                ),
            )
