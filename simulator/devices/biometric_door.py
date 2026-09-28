from shared.commands import DoorCommand
from shared.devices import Device


class BiometricDoorSimulator:
    def __init__(self, device: Device):
        self.device = device
        self.locked = True

    def apply_command(self, command: DoorCommand):
        self.locked = command.locked

        return {
            "device_id": self.device.device_id,
            "room_id": self.device.room_id,
            "locked": self.locked,
        }

    def get_state(self):
        return {
            "device_id": self.device.device_id,
            "room_id": self.device.room_id,
            "locked": self.locked,
        }
