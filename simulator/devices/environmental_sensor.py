"""Simulates an environmental sensor and publishes via its registered transport."""

import asyncio

import httpx

from shared.devices import Device
from shared.telemetry import EnvironmentalTelemetry
from simulator.integrations.telemetry import send_device_telemetry


class EnvironmentalSensorSimulator:
    def __init__(
        self, device: Device, facility_url: str, gateway_url: str, interval: int = 2
    ):
        self.device = device
        self.facility_url = facility_url
        self.gateway_url = gateway_url
        self.interval = interval

    def create_telemetry(
        self, temperature: float, humidity: float
    ) -> EnvironmentalTelemetry:
        return EnvironmentalTelemetry(
            device_id=self.device.device_id,
            room_id=self.device.room_id,
            temperature=round(temperature, 2),
            humidity=round(humidity, 2),
        )

    async def run(self):
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    response = await client.get(
                        f"{self.facility_url}/environments/{self.device.room_id}"
                    )
                    response.raise_for_status()
                    environment = response.json()
                    telemetry = self.create_telemetry(
                        environment["temperature"], environment["humidity"]
                    )
                    await send_device_telemetry(
                        self.device,
                        "environmental",
                        telemetry.model_dump(),
                        self.gateway_url,
                    )
                    print(
                        f"[{self.device.device_id}] {self.device.protocol.value.upper()} "
                        f"environmental telemetry: {telemetry.model_dump()}"
                    )
                except Exception as exc:
                    print(f"[{self.device.device_id}] telemetry error: {exc}")
                await asyncio.sleep(self.interval)
