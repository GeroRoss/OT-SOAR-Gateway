"""Response strategies for logical containment and actuator safety actions."""

from enum import Enum

from pydantic import BaseModel


class ResponseStrategy(str, Enum):
    LOGICAL_CONTAINMENT = "logical_containment"
    PRESERVE_SAFE_OPERATION = "preserve_safe_operation"
    EMERGENCY_POWER_ISOLATION = "emergency_power_isolation"
    FAIL_SAFE_COOLING = "fail_safe_cooling"
    EMERGENCY_EGRESS = "emergency_egress"
    SECURE_DOOR = "secure_door"
    MANUAL_SAFETY_VERIFICATION = "manual_safety_verification"


class ResponseRecord(BaseModel):
    response_id: int
    started_at: str
    completed_at: str | None = None
    device_id: str
    room_id: str
    device_type: str
    criticality: str
    trigger_reason: str
    strategy: ResponseStrategy
    action: str
    success: bool
    outcome: str
    safety_context: dict
    duration_ms: float | None = None
