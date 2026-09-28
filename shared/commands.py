"""Actuator commands and requests from personnel or registered devices.

Requests carry a person_id or source_device_id. The gateway looks up the
role, room, device type, and security state instead of accepting those
authorization attributes from the caller."""

from pydantic import BaseModel, Field


class HVACCommand(BaseModel):
    cooling_level: int = Field(ge=0, le=100)


class PDUCommand(BaseModel):
    power_on: bool


class DoorCommand(BaseModel):
    locked: bool


class HVACControlRequest(BaseModel):
    person_id: str
    command: HVACCommand


class PDUControlRequest(BaseModel):
    person_id: str
    command: PDUCommand


class DoorControlRequest(BaseModel):
    person_id: str
    command: DoorCommand


class DeviceHVACControlRequest(BaseModel):
    source_device_id: str
    command: HVACCommand


class DevicePDUControlRequest(BaseModel):
    source_device_id: str
    command: PDUCommand


class DeviceDoorControlRequest(BaseModel):
    source_device_id: str
    command: DoorCommand


class DoorAccessRequest(BaseModel):
    person_id: str
