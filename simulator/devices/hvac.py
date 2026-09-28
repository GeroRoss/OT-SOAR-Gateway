from shared.commands import HVACCommand
from shared.devices import Device


class HVACSimulator:
    def __init__(self, device: Device):
        self.device = device

    def apply_command(self, environment, command: HVACCommand):
        environment.cooling_level = command.cooling_level

        return {
            "device_id": self.device.device_id,
            "room_id": self.device.room_id,
            "cooling_level": environment.cooling_level,
        }
