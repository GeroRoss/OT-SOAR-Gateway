"""Automation rule models. ABAC authorization uses separate policy models."""

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from shared.devices import DeviceType, SecurityState


class IoTTriggerAttribute(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    SMOKE_LEVEL = "smoke_level"
    VOLTAGE = "voltage"
    CURRENT = "current"
    POWER = "power"
    POWER_ON = "power_on"


class IoTConditionOperator(str, Enum):
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    EQUAL = "equal"


class IoTTargetScope(str, Enum):
    SAME_ROOM = "same_room"
    WHOLE_FACILITY = "whole_facility"


class IoTAction(str, Enum):
    SET_COOLING = "set_cooling"
    SET_POWER = "set_power"
    SET_LOCKED = "set_locked"


SOURCE_ATTRIBUTES = {
    DeviceType.ENVIRONMENTAL_SENSOR: {
        IoTTriggerAttribute.TEMPERATURE,
        IoTTriggerAttribute.HUMIDITY,
    },
    DeviceType.SMOKE_SENSOR: {IoTTriggerAttribute.SMOKE_LEVEL},
    DeviceType.PDU: {
        IoTTriggerAttribute.VOLTAGE,
        IoTTriggerAttribute.CURRENT,
        IoTTriggerAttribute.POWER,
        IoTTriggerAttribute.POWER_ON,
    },
}

TARGET_ACTIONS = {
    DeviceType.HVAC: {IoTAction.SET_COOLING},
    DeviceType.PDU: {IoTAction.SET_POWER},
    DeviceType.BIOMETRIC_DOOR: {IoTAction.SET_LOCKED},
}


class IoTDevicePolicyBase(BaseModel):
    """A reusable desired-state rule resolved against registered devices at runtime."""

    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    trigger_device_type: DeviceType
    trigger_attribute: IoTTriggerAttribute
    operator: IoTConditionOperator
    threshold: float
    required_source_state: SecurityState = SecurityState.NORMAL
    target_device_type: DeviceType
    target_scope: IoTTargetScope = IoTTargetScope.SAME_ROOM
    action: IoTAction
    action_value: int = Field(ge=0, le=100)
    fallback_value: int | None = Field(default=None, ge=0, le=100)
    priority: int = Field(default=5, ge=1, le=9)

    @model_validator(mode="after")
    def validate_capabilities(self):
        if self.required_source_state == SecurityState.QUARANTINED:
            raise ValueError(
                "Quarantined devices cannot be IoT policy sources because "
                "their telemetry is rejected by the gateway trust boundary"
            )

        allowed_attributes = SOURCE_ATTRIBUTES.get(self.trigger_device_type, set())
        if self.trigger_attribute not in allowed_attributes:
            raise ValueError(
                f"{self.trigger_device_type.value} does not publish "
                f"{self.trigger_attribute.value}"
            )

        allowed_actions = TARGET_ACTIONS.get(self.target_device_type, set())
        if self.action not in allowed_actions:
            raise ValueError(
                f"{self.target_device_type.value} does not support {self.action.value}"
            )

        if self.action in {IoTAction.SET_POWER, IoTAction.SET_LOCKED}:
            if self.action_value not in {0, 1}:
                raise ValueError(f"{self.action.value} action_value must be 0 or 1")
            if self.fallback_value is not None and self.fallback_value not in {0, 1}:
                raise ValueError(f"{self.action.value} fallback_value must be 0 or 1")

        return self


class IoTDevicePolicy(IoTDevicePolicyBase):
    policy_id: str


class IoTDevicePolicyCreate(IoTDevicePolicyBase):
    pass


class IoTDevicePolicyUpdate(IoTDevicePolicyBase):
    pass
