"""HTTP calls from the gateway to the facility simulator."""

import httpx

from shared.commands import DoorCommand, HVACCommand, PDUCommand

FACILITY_URL = "http://facility:8001"


async def _request(method: str, path: str, payload: dict | None = None):
    async with httpx.AsyncClient() as client:
        response = await client.request(method, f"{FACILITY_URL}{path}", json=payload)
        response.raise_for_status()
        return response.json()


async def refresh_simulated_rooms():
    try:
        await _request("POST", "/environments/refresh")
    except httpx.HTTPError as exc:
        print(f"[gateway] simulator room refresh failed: {exc}")


async def refresh_simulated_devices():
    try:
        await _request("POST", "/devices/refresh")
    except httpx.HTTPError as exc:
        print(f"[gateway] simulator device refresh failed: {exc}")


async def send_hvac_command(device_id: str, command: HVACCommand):
    return await _request(
        "POST", f"/devices/{device_id}/commands/hvac", command.model_dump()
    )


async def send_pdu_command(device_id: str, command: PDUCommand):
    return await _request(
        "POST", f"/devices/{device_id}/commands/pdu", command.model_dump()
    )


async def send_door_command(device_id: str, command: DoorCommand):
    return await _request(
        "POST", f"/devices/{device_id}/commands/door", command.model_dump()
    )


async def get_simulated_environments():
    return await _request("GET", "/environments")


async def get_simulated_device_state(device_id: str):
    return await _request("GET", f"/devices/{device_id}/state")


async def update_simulated_environment(room_id: str, payload: dict):
    return await _request("PUT", f"/environments/{room_id}", payload)


async def quiesce_simulator_demo_state():
    """Stop simulator publishers before gateway persistence is replaced."""

    return await _request("POST", "/development/quiesce")


async def rebuild_simulator_demo_state():
    """Rebuild simulator state from the gateway's freshly seeded registry."""

    return await _request("POST", "/development/rebuild")


async def launch_attack(payload: dict):
    return await _request("POST", "/attacks/launch", payload)


async def get_attack_status():
    return await _request("GET", "/attacks/status")


def _request_sync(method: str, path: str, payload: dict | None = None):
    """Synchronous simulator request used by the background response engine."""

    with httpx.Client(timeout=5.0) as client:
        response = client.request(method, f"{FACILITY_URL}{path}", json=payload)
        response.raise_for_status()
        return response.json()


def get_simulated_environment_sync(room_id: str):
    return _request_sync("GET", f"/environments/{room_id}")


def get_simulated_device_state_sync(device_id: str):
    return _request_sync("GET", f"/devices/{device_id}/state")


def send_hvac_command_sync(device_id: str, command: HVACCommand):
    return _request_sync(
        "POST", f"/devices/{device_id}/commands/hvac", command.model_dump()
    )


def send_pdu_command_sync(device_id: str, command: PDUCommand):
    return _request_sync(
        "POST", f"/devices/{device_id}/commands/pdu", command.model_dump()
    )


def send_door_command_sync(device_id: str, command: DoorCommand):
    return _request_sync(
        "POST", f"/devices/{device_id}/commands/door", command.model_dump()
    )
