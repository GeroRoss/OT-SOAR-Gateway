import httpx

from shared.devices import Device, DeviceType
from shared.rooms import Room

from simulator.devices.biometric_door import BiometricDoorSimulator
from simulator.devices.environmental_sensor import EnvironmentalSensorSimulator
from simulator.devices.hvac import HVACSimulator
from simulator.devices.pdu import PDUSimulator
from simulator.devices.smoke_sensor import SmokeSensorSimulator

FACILITY_URL = "http://facility:8001"
GATEWAY_URL = "http://gateway:8000"


def create_simulator(device: Device):
    if device.device_type == DeviceType.ENVIRONMENTAL_SENSOR:
        return EnvironmentalSensorSimulator(
            device=device, facility_url=FACILITY_URL, gateway_url=GATEWAY_URL
        )

    if device.device_type == DeviceType.SMOKE_SENSOR:
        return SmokeSensorSimulator(
            device=device, facility_url=FACILITY_URL, gateway_url=GATEWAY_URL
        )

    if device.device_type == DeviceType.PDU:
        return PDUSimulator(
            device=device, facility_url=FACILITY_URL, gateway_url=GATEWAY_URL
        )

    if device.device_type == DeviceType.HVAC:
        return HVACSimulator(device=device)

    if device.device_type == DeviceType.BIOMETRIC_DOOR:
        return BiometricDoorSimulator(device=device)

    raise ValueError(f"Unsupported device type: {device.device_type}")


async def fetch_registered_devices() -> list[Device]:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{GATEWAY_URL}/devices")
        response.raise_for_status()

        return [Device(**device_data) for device_data in response.json()]


async def fetch_registered_rooms() -> list[Room]:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{GATEWAY_URL}/rooms")
        response.raise_for_status()

        return [Room(**room_data) for room_data in response.json()]


async def build_device_simulators():
    devices = await fetch_registered_devices()

    simulators = {}

    for device in devices:
        try:
            simulators[device.device_id] = create_simulator(device)

        except ValueError:
            continue

    return simulators
