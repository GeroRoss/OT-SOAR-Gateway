"""Simulates a smoke sensor and publishes via its registered transport."""

import asyncio

import httpx

from shared.devices import Device
from shared.telemetry import SmokeTelemetry
from simulator.integrations.telemetry import send_device_telemetry


class SmokeSensorSimulator:
    def __init__(
        self, device: Device, facility_url: str, gateway_url: str, interval: int = 2
    ):
        self.device = device
        self.facility_url = facility_url
        self.gateway_url = gateway_url
        self.interval = interval

    async def run(self):
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    response = await client.get(
                        f"{self.facility_url}/environments/{self.device.room_id}"
                    )
                    response.raise_for_status()
                    environment = response.json()
                    telemetry = SmokeTelemetry(
                        device_id=self.device.device_id,
                        room_id=self.device.room_id,
                        smoke_level=round(environment["smoke_level"], 2),
                    )
                    await send_device_telemetry(
                        self.device, "smoke", telemetry.model_dump(), self.gateway_url
                    )
                    print(
                        f"[{self.device.device_id}] {self.device.protocol.value.upper()} "
                        f"smoke telemetry: {telemetry.model_dump()}"
                    )
                except Exception as exc:
                    print(f"[{self.device.device_id}] telemetry error: {exc}")
                await asyncio.sleep(self.interval)
