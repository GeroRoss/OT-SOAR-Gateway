import asyncio

import httpx

from shared.commands import PDUCommand
from shared.devices import Device
from shared.telemetry import PDUTelemetry


class PDUSimulator:
    def __init__(
        self, device: Device, facility_url: str, gateway_url: str, interval: int = 2
    ):
        self.device = device
        self.facility_url = facility_url
        self.gateway_url = gateway_url
        self.interval = interval

    def create_telemetry(self, power_on: bool) -> PDUTelemetry:
        if power_on:
            voltage = 230.0
            current = 12.5
            power = voltage * current

        else:
            voltage = 0.0
            current = 0.0
            power = 0.0

        return PDUTelemetry(
            device_id=self.device.device_id,
            room_id=self.device.room_id,
            voltage=voltage,
            current=current,
            power=power,
            power_on=power_on,
        )

    def apply_command(self, environment, command: PDUCommand):
        environment.power_available = command.power_on

        return {
            "device_id": self.device.device_id,
            "room_id": self.device.room_id,
            "power_on": environment.power_available,
        }

    async def run(self):
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    response = await client.get(
                        f"{self.facility_url}/environments/" f"{self.device.room_id}"
                    )
                    response.raise_for_status()

                    environment = response.json()

                    telemetry = self.create_telemetry(
                        power_on=environment["power_available"]
                    )

                    response = await client.post(
                        f"{self.gateway_url}/telemetry/pdu", json=telemetry.model_dump()
                    )
                    response.raise_for_status()

                    print(
                        f"[{self.device.device_id}] "
                        f"PDU telemetry: "
                        f"{telemetry.model_dump()}"
                    )

                except Exception as exc:
                    print(f"[{self.device.device_id}] " f"telemetry error: {exc}")

                await asyncio.sleep(self.interval)
