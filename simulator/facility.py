"""Simulated room conditions, device tasks, and development attack scenarios."""

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.commands import DoorCommand, HVACCommand, PDUCommand
from shared.devices import DeviceType
from shared.telemetry import EnvironmentalTelemetry, PDUTelemetry, SmokeTelemetry
from simulator.device_manager import build_device_simulators, fetch_registered_rooms
from simulator.integrations.telemetry import (
    begin_telemetry_reset,
    end_telemetry_reset,
    send_device_telemetry,
)

GATEWAY_URL = "http://gateway:8000"

GATEWAY_STARTUP_ATTEMPTS = 30
GATEWAY_STARTUP_DELAY_SECONDS = 1.0


class RoomEnvironment(BaseModel):
    room_id: str
    temperature: float
    humidity: float
    smoke_level: float = 0.0
    cooling_level: int = 35
    power_available: bool = True


class EnvironmentUpdateRequest(BaseModel):
    temperature: float | None = Field(default=None, ge=-20, le=100)
    humidity: float | None = Field(default=None, ge=0, le=100)
    smoke_level: float | None = Field(default=None, ge=0, le=100)
    power_available: bool | None = None


class AttackRequest(BaseModel):
    device_id: str
    attack_type: str
    rate_per_second: int = Field(default=1, ge=1, le=100)
    duration_seconds: int = Field(default=5, ge=1, le=60)


environments: dict[str, RoomEnvironment] = {}
device_simulators = {}
device_tasks = {}
active_attacks: dict[str, dict] = {}
attack_tasks: dict[str, asyncio.Task] = {}


async def wait_for_gateway() -> None:
    """Wait until the gateway health endpoint is ready.

    Docker Compose start ordering does not imply application readiness.
    The facility therefore performs a bounded retry before loading the
    gateway-owned room and device registries.
    """

    last_error = None

    async with httpx.AsyncClient(timeout=2.0) as client:
        for attempt in range(1, GATEWAY_STARTUP_ATTEMPTS + 1):
            try:
                response = await client.get(f"{GATEWAY_URL}/health")
                response.raise_for_status()

                print("[facility] gateway is ready " f"after {attempt} attempt(s)")
                return

            except httpx.HTTPError as exc:
                last_error = exc

                if attempt == 1 or attempt % 5 == 0:
                    print(
                        "[facility] waiting for gateway "
                        f"({attempt}/"
                        f"{GATEWAY_STARTUP_ATTEMPTS}): "
                        f"{exc}"
                    )

                await asyncio.sleep(GATEWAY_STARTUP_DELAY_SECONDS)

    raise RuntimeError(
        "Gateway did not become ready within "
        f"{GATEWAY_STARTUP_ATTEMPTS * GATEWAY_STARTUP_DELAY_SECONDS:.0f} "
        f"seconds. Last error: {last_error}"
    )


def create_environment(room_id: str) -> RoomEnvironment:
    return RoomEnvironment(
        room_id=room_id,
        temperature=24.0,
        humidity=45.0,
        smoke_level=0.0,
        cooling_level=35,
        power_available=True,
    )


def update_environment(environment: RoomEnvironment):
    """Advance simplified room physics without making control decisions.

    The simulator models the physical effect of whatever HVAC level the
    gateway has commanded. It does not choose that level itself: the IoT
    device policy engine in the gateway owns automation decisions.
    """

    NORMAL_TEMPERATURE_FLOOR = 24.0
    NORMAL_HUMIDITY_FLOOR = 40.0
    SMOKE_FLOOR = 0.0

    if not environment.power_available:
        # Residual heat continues after loss of server power.
        # Powered HVAC is unavailable. Humidity and smoke remain stable.
        environment.temperature = min(environment.temperature + 0.02, 80.0)
        return

    # Powered equipment continuously generates heat.
    heat_generation = 0.18
    cooling_effect = environment.cooling_level * 0.006

    environment.temperature += heat_generation - cooling_effect

    environment.temperature = max(
        NORMAL_TEMPERATURE_FLOOR, min(environment.temperature, 80.0)
    )

    # Humidity and smoke only rise through explicit simulation input.
    # HVAC represents simplified dehumidification and smoke extraction.
    if environment.humidity > NORMAL_HUMIDITY_FLOOR:
        environment.humidity -= environment.cooling_level * 0.003

        environment.humidity = max(NORMAL_HUMIDITY_FLOOR, environment.humidity)

    if environment.smoke_level > SMOKE_FLOOR:
        environment.smoke_level -= environment.cooling_level * 0.01

        environment.smoke_level = max(SMOKE_FLOOR, environment.smoke_level)


async def simulation_loop():
    while True:
        for environment in environments.values():
            update_environment(environment)

        await asyncio.sleep(1)


async def refresh_environments():
    registered_rooms = await fetch_registered_rooms()
    registered_ids = {room.room_id for room in registered_rooms}

    added_rooms = []
    removed_rooms = []

    for room_id in list(environments):
        if room_id not in registered_ids:
            environments.pop(room_id, None)
            removed_rooms.append(room_id)

    for room in registered_rooms:
        if room.room_id not in environments:
            environments[room.room_id] = create_environment(room.room_id)
            added_rooms.append(room.room_id)

    return {"added_rooms": added_rooms, "removed_rooms": removed_rooms}


async def refresh_device_simulators():
    """Reconcile simulator tasks with the gateway device registry."""

    discovered_simulators = await build_device_simulators()

    added_devices = []
    removed_devices = []

    for device_id in list(device_simulators):
        current = device_simulators[device_id]

        discovered = discovered_simulators.get(device_id)

        changed = (
            discovered is not None
            and current.device.model_dump() != discovered.device.model_dump()
        )

        if discovered is None or changed:
            task = device_tasks.pop(device_id, None)

            if task:
                task.cancel()

            device_simulators.pop(device_id, None)

            removed_devices.append(device_id)

    for device_id, simulator in discovered_simulators.items():
        if device_id in device_simulators:
            continue

        device_simulators[device_id] = simulator

        if hasattr(simulator, "run"):
            device_tasks[device_id] = asyncio.create_task(simulator.run())

        added_devices.append(device_id)

    return {"added_devices": added_devices, "removed_devices": removed_devices}


async def _send_attack_telemetry(
    device_id: str, room_id: str, *, temperature_offset: float = 0.0
):
    simulator = device_simulators[device_id]

    environment = environments[simulator.device.room_id]

    device_type = simulator.device.device_type

    if device_type == DeviceType.ENVIRONMENTAL_SENSOR:
        payload = EnvironmentalTelemetry(
            device_id=device_id,
            room_id=room_id,
            temperature=round(environment.temperature + temperature_offset, 2),
            humidity=round(environment.humidity, 2),
        ).model_dump()

        path = "/telemetry/environmental"

    elif device_type == DeviceType.SMOKE_SENSOR:
        payload = SmokeTelemetry(
            device_id=device_id,
            room_id=room_id,
            smoke_level=round(environment.smoke_level, 2),
        ).model_dump()

        path = "/telemetry/smoke"

    elif device_type == DeviceType.PDU:
        payload = PDUTelemetry(
            device_id=device_id,
            room_id=room_id,
            voltage=(230.0 if environment.power_available else 0.0),
            current=(12.5 if environment.power_available else 0.0),
            power=(2875.0 if environment.power_available else 0.0),
            power_on=(environment.power_available),
        ).model_dump()

        path = "/telemetry/pdu"

    else:
        raise ValueError("Attack target does not publish " "supported telemetry")

    telemetry_type = path.rsplit("/", 1)[-1]

    try:
        await send_device_telemetry(
            simulator.device, telemetry_type, payload, GATEWAY_URL
        )

    except Exception as exc:
        # Do not silently count an attack telemetry attempt as successful when
        # publication failed. Propagate the failure so the attack run is marked
        # failed and the evaluation can distinguish transport faults from a
        # successful attack that the detector missed.
        raise RuntimeError(
            f"Attack telemetry publication failed for {device_id}: {exc}"
        ) from exc


async def _send_unauthorized_control_attempt(source_device_id: str):
    """Simulate lateral movement from a compromised registered device."""

    source = device_simulators[source_device_id].device

    candidates = [
        simulator.device
        for (device_id, simulator) in device_simulators.items()
        if (
            device_id != source_device_id
            and simulator.device.device_type
            in {DeviceType.HVAC, DeviceType.PDU, DeviceType.BIOMETRIC_DOOR}
        )
    ]

    if not candidates:
        raise ValueError(
            "No separate actuator is available " "as a lateral-movement target"
        )

    candidates.sort(key=lambda device: (device.room_id == source.room_id))

    target = candidates[0]

    if target.device_type == DeviceType.HVAC:
        path = f"/devices/{target.device_id}" "/commands/device/hvac"

        payload = {
            "source_device_id": source_device_id,
            "command": {"cooling_level": 0},
        }

    elif target.device_type == DeviceType.PDU:
        path = f"/devices/{target.device_id}" "/commands/device/pdu"

        payload = {"source_device_id": source_device_id, "command": {"power_on": False}}

    else:
        path = f"/devices/{target.device_id}" "/commands/device/door"

        payload = {"source_device_id": source_device_id, "command": {"locked": False}}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{GATEWAY_URL}{path}", json=payload)

            return (target.device_id, response.status_code)

        except httpx.HTTPError:
            return (target.device_id, 503)


async def _run_attack(request: AttackRequest):
    attack_id = f"{request.attack_type}:" f"{request.device_id}"

    simulator = device_simulators[request.device_id]

    active_attacks[attack_id] = {
        "attack_id": attack_id,
        "device_id": request.device_id,
        "attack_type": request.attack_type,
        "status": "running",
        "rate_per_second": request.rate_per_second,
        "duration_seconds": request.duration_seconds,
        "attempts": 0,
        "denied_attempts": 0,
    }

    try:
        if request.attack_type == "slow_poisoning":
            # Time-compressed representation of a low-and-slow integrity
            # attack. The compromised sensor replaces its normal 2-second
            # publication rather than adding traffic, so the message-rate
            # detector alone should not identify it.
            interval = 2.0
            iterations = max(1, int(request.duration_seconds / interval))
        else:
            interval = 1 / request.rate_per_second
            iterations = request.rate_per_second * request.duration_seconds

        normal_room = simulator.device.room_id

        wrong_room = next(
            (room_id for room_id in environments if room_id != normal_room),
            "unknown-room",
        )

        paused_normal_task = None
        if request.attack_type == "slow_poisoning":
            paused_normal_task = device_tasks.pop(request.device_id, None)
            if paused_normal_task is not None:
                paused_normal_task.cancel()
                await asyncio.gather(paused_normal_task, return_exceptions=True)

        for iteration in range(iterations):
            if request.attack_type == "unauthorized_control":
                target_device_id, status_code = (
                    await _send_unauthorized_control_attempt(request.device_id)
                )

                active_attacks[attack_id]["target_device_id"] = target_device_id

                active_attacks[attack_id]["attempts"] += 1

                if status_code == 403:
                    active_attacks[attack_id]["denied_attempts"] += 1

            else:
                if request.attack_type == "wrong_room":
                    room_id = wrong_room
                    temperature_offset = 0.0
                elif request.attack_type == "slow_poisoning":
                    room_id = normal_room
                    # Each replacement sample drifts a little farther from
                    # the real shared room condition. With two healthy peers,
                    # the gateway can identify the disagreement without a
                    # message-rate anomaly.
                    temperature_offset = (iteration + 1) * 1.5
                    active_attacks[attack_id]["temperature_offset"] = round(
                        temperature_offset, 2
                    )
                else:
                    room_id = normal_room
                    temperature_offset = 0.0

                await _send_attack_telemetry(
                    request.device_id, room_id, temperature_offset=temperature_offset
                )

                active_attacks[attack_id]["attempts"] += 1

            await asyncio.sleep(interval)

        if (
            request.attack_type == "slow_poisoning"
            and request.device_id not in device_tasks
        ):
            simulator_instance = device_simulators.get(request.device_id)
            if simulator_instance is not None and hasattr(simulator_instance, "run"):
                device_tasks[request.device_id] = asyncio.create_task(
                    simulator_instance.run()
                )

        active_attacks[attack_id]["status"] = "completed"

    except asyncio.CancelledError:
        active_attacks[attack_id]["status"] = "cancelled"
        raise

    except Exception as exc:
        active_attacks[attack_id]["status"] = "failed"

        active_attacks[attack_id]["error"] = str(exc)


async def _cancel_and_await_tasks(tasks: dict[str, asyncio.Task]) -> None:
    """Cancel a task collection and wait until every asyncio task has stopped."""

    pending = list(tasks.values())

    for task in pending:
        task.cancel()

    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    tasks.clear()


async def quiesce_development_state():
    """Stop all simulator publishers before the gateway seed is replaced."""

    # Invalidate MQTT work before cancelling tasks. This prevents a publish
    # already queued in asyncio.to_thread() from crossing the reset boundary.
    await asyncio.to_thread(begin_telemetry_reset)

    await _cancel_and_await_tasks(attack_tasks)
    active_attacks.clear()

    await _cancel_and_await_tasks(device_tasks)
    device_simulators.clear()
    environments.clear()

    return {"status": "quiesced", "rooms": [], "devices": []}


async def rebuild_development_state():
    """Rebuild simulator state from the gateway's current seeded registry."""

    await refresh_environments()

    # All old publisher tasks were cancelled and awaited by quiesce.  Enable
    # the new telemetry generation *before* new tasks are created so their
    # first sample is not nondeterministically dropped while reset is still
    # marked quiesced.  The gateway reset path has already waited for MQTT
    # SUBACK before calling this endpoint.
    await asyncio.to_thread(end_telemetry_reset)

    changes = await refresh_device_simulators()

    return {
        "status": "reset",
        "rooms": list(environments.keys()),
        "devices": list(device_simulators.keys()),
        **changes,
    }


async def reset_development_state():
    """Backward-compatible complete simulator reset."""

    await quiesce_development_state()
    return await rebuild_development_state()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wait for gateway readiness before constructing facility state."""

    await wait_for_gateway()

    await refresh_environments()
    await refresh_device_simulators()

    simulation_task = asyncio.create_task(simulation_loop())

    print(
        "[facility] simulator startup complete: "
        f"{len(environments)} room(s), "
        f"{len(device_simulators)} device(s)"
    )

    try:
        yield

    finally:
        simulation_task.cancel()

        for task in device_tasks.values():
            task.cancel()

        for task in attack_tasks.values():
            task.cancel()


app = FastAPI(title="Facility Simulator", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "rooms": len(environments),
        "devices": len(device_simulators),
    }


@app.get("/environments")
def list_environments():
    return list(environments.values())


@app.get("/environments/{room_id}")
def get_environment(room_id: str):
    environment = environments.get(room_id)

    if environment is None:
        raise HTTPException(status_code=404, detail=("Room environment not found"))

    return environment


@app.put("/environments/{room_id}")
def set_environment(room_id: str, request: EnvironmentUpdateRequest):
    environment = environments.get(room_id)

    if environment is None:
        raise HTTPException(status_code=404, detail=("Room environment not found"))

    for field, value in request.model_dump(exclude_none=True).items():
        setattr(environment, field, value)

    return environment


@app.post("/environments/refresh")
async def refresh_room_environments():
    changes = await refresh_environments()

    return {"status": "refreshed", **changes, "active_rooms": list(environments.keys())}


@app.post("/devices/refresh")
async def refresh_devices():
    changes = await refresh_device_simulators()

    return {
        "status": "refreshed",
        **changes,
        "active_devices": list(device_simulators.keys()),
    }


@app.get("/devices")
def list_devices():
    return list(device_simulators.keys())


@app.get("/devices/{device_id}/state")
def get_device_state(device_id: str):
    simulator = device_simulators.get(device_id)

    if simulator is None:
        raise HTTPException(status_code=404, detail=("Simulated device not found"))

    if hasattr(simulator, "get_state"):
        return simulator.get_state()

    environment = environments.get(simulator.device.room_id)

    if environment is None:
        raise HTTPException(
            status_code=404, detail=("Device room environment not found")
        )

    return {
        "device_id": simulator.device.device_id,
        "room_id": simulator.device.room_id,
        "device_type": simulator.device.device_type,
        "environment": environment,
    }


@app.post("/devices/{device_id}/commands/hvac")
def command_hvac(device_id: str, command: HVACCommand):
    simulator = device_simulators.get(device_id)

    if simulator is None:
        raise HTTPException(status_code=404, detail=("Simulated device not found"))

    if simulator.device.device_type != DeviceType.HVAC:
        raise HTTPException(status_code=400, detail=("Device is not an HVAC actuator"))

    environment = environments.get(simulator.device.room_id)

    if environment is None:
        raise HTTPException(status_code=404, detail=("HVAC room environment not found"))

    return simulator.apply_command(environment, command)


@app.post("/devices/{device_id}/commands/pdu")
def command_pdu(device_id: str, command: PDUCommand):
    simulator = device_simulators.get(device_id)

    if simulator is None:
        raise HTTPException(status_code=404, detail=("Simulated device not found"))

    if simulator.device.device_type != DeviceType.PDU:
        raise HTTPException(status_code=400, detail="Device is not a PDU")

    environment = environments.get(simulator.device.room_id)

    if environment is None:
        raise HTTPException(status_code=404, detail=("PDU room environment not found"))

    return simulator.apply_command(environment, command)


@app.post("/devices/{device_id}/commands/door")
def command_door(device_id: str, command: DoorCommand):
    simulator = device_simulators.get(device_id)

    if simulator is None:
        raise HTTPException(status_code=404, detail=("Simulated device not found"))

    if simulator.device.device_type != DeviceType.BIOMETRIC_DOOR:
        raise HTTPException(status_code=400, detail=("Device is not a biometric door"))

    return simulator.apply_command(command)


@app.post("/development/quiesce")
async def quiesce_demo_simulator():
    """Stop simulator publishers before gateway persistence is reset."""

    return await quiesce_development_state()


@app.post("/development/rebuild")
async def rebuild_demo_simulator():
    """Rebuild simulator publishers after gateway persistence is reseeded."""

    return await rebuild_development_state()


@app.post("/development/reset")
async def reset_demo_simulator():
    """Development-only complete reset retained for direct compatibility."""

    return await reset_development_state()


@app.post("/attacks/launch", status_code=202)
async def launch_attack(request: AttackRequest):
    simulator = device_simulators.get(request.device_id)

    if simulator is None:
        raise HTTPException(status_code=404, detail=("Simulated device not found"))

    if request.attack_type not in {
        "telemetry_flood",
        "wrong_room",
        "slow_poisoning",
        "unauthorized_control",
    }:
        raise HTTPException(status_code=400, detail="Unsupported attack type")

    if request.attack_type in {
        "telemetry_flood",
        "wrong_room",
        "slow_poisoning",
    } and simulator.device.device_type not in {
        DeviceType.ENVIRONMENTAL_SENSOR,
        DeviceType.SMOKE_SENSOR,
        DeviceType.PDU,
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "Telemetry attacks require an environmental, "
                "smoke, or PDU telemetry source"
            ),
        )

    if (
        request.attack_type == "slow_poisoning"
        and simulator.device.device_type != DeviceType.ENVIRONMENTAL_SENSOR
    ):
        raise HTTPException(
            status_code=400, detail="Slow poisoning requires an environmental sensor"
        )

    if request.attack_type == "unauthorized_control":
        has_target = any(
            (
                device_id != request.device_id
                and candidate.device.device_type
                in {DeviceType.HVAC, DeviceType.PDU, DeviceType.BIOMETRIC_DOOR}
            )
            for (device_id, candidate) in device_simulators.items()
        )

        if not has_target:
            raise HTTPException(
                status_code=400,
                detail=("No separate actuator is available " "as an attack target"),
            )

    attack_id = f"{request.attack_type}:" f"{request.device_id}"

    existing = active_attacks.get(attack_id)

    if existing and existing["status"] == "running":
        raise HTTPException(status_code=409, detail=("Attack is already running"))

    task = asyncio.create_task(_run_attack(request))

    attack_tasks[attack_id] = task

    return {"status": "launched", "attack_id": attack_id}


@app.get("/attacks/status")
def get_attacks():
    return list(active_attacks.values())
