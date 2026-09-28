from pydantic import BaseModel


class EnvironmentalTelemetry(BaseModel):
    device_id: str
    room_id: str
    temperature: float
    humidity: float


class SmokeTelemetry(BaseModel):
    device_id: str
    room_id: str
    smoke_level: float


class PDUTelemetry(BaseModel):
    device_id: str
    room_id: str
    voltage: float
    current: float
    power: float
    power_on: bool
