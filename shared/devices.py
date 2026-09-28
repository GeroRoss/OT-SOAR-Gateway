"""Device records and registration payloads shared by gateway and simulator."""

from enum import Enum
from pydantic import BaseModel


class DeviceType(str, Enum):
    ENVIRONMENTAL_SENSOR = "environmental_sensor"
    PDU = "pdu"
    HVAC = "hvac"
    BIOMETRIC_DOOR = "biometric_door"
    SMOKE_SENSOR = "smoke_sensor"


class Protocol(str, Enum):
    HTTP = "http"
    MQTT = "mqtt"


class SecurityState(str, Enum):
    NORMAL = "normal"
    SUSPICIOUS = "suspicious"
    QUARANTINED = "quarantined"


class Criticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SAFETY_CRITICAL = "safety_critical"


class Device(BaseModel):
    device_id: str
    name: str
    device_type: DeviceType
    room_id: str
    protocol: Protocol
    criticality: Criticality
    security_state: SecurityState = SecurityState.NORMAL


class DeviceRegistrationRequest(BaseModel):
    """Operator input; security-relevant defaults and device_id are gateway-owned."""

    device_type: DeviceType
    room_id: str
    name: str | None = None


class DeviceRegistrationPreview(BaseModel):
    device_id: str
    name: str
    protocol: Protocol
    criticality: Criticality


class DeviceUpdateRequest(BaseModel):
    """Editable device metadata. Stable identity/type/defaults are excluded."""

    name: str
    room_id: str
