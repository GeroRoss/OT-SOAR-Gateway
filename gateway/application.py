"""Create the gateway API, seed its data, and start MQTT ingestion."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateway.access.routes import router as access_router
from gateway.attack.routes import router as attack_router
from gateway.control.routes import router as control_router
from gateway.database import initialise_database
from gateway.events.routes import router as events_router
from gateway.infrastructure.devices.defaults import (
    reconcile_registered_device_protocols,
)
from gateway.infrastructure.devices.routes import router as devices_router
from gateway.infrastructure.rooms.routes import router as rooms_router
from gateway.integrations.mqtt import start_mqtt_ingestion, stop_mqtt_ingestion
from gateway.iot_policy.repository import (
    migrate_iot_policy_ids_to_numeric,
    migrate_predefined_hvac_baseline_to_35,
    migrate_iot_policy_priorities_to_1_9,
    migrate_legacy_iot_policies,
    seed_predefined_iot_policies,
)
from gateway.iot_policy.routes import router as iot_policy_router
from gateway.personnel.routes import router as personnel_router
from gateway.personnel.seed import seed_personnel
from gateway.policy.defaults import seed_default_policies
from gateway.policy.routes import router as policy_router
from gateway.response.routes import router as response_router
from gateway.security.routes import router as security_router
from gateway.seed import seed_database
from gateway.simulation.routes import router as simulation_router
from gateway.system.routes import router as system_router
from gateway.telemetry.routes import router as telemetry_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise_database()
    seed_database()
    reconcile_registered_device_protocols()
    seed_default_policies()
    migrate_legacy_iot_policies()
    seed_predefined_iot_policies()
    migrate_iot_policy_ids_to_numeric()
    migrate_predefined_hvac_baseline_to_35()
    migrate_iot_policy_priorities_to_1_9()
    seed_personnel()
    start_mqtt_ingestion()
    yield
    stop_mqtt_ingestion()


app = FastAPI(
    title="OT-SOAR Gateway",
    description=(
        "Management, monitoring and security API for the OT-SOAR "
        "safety-critical IoT gateway."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(rooms_router)
app.include_router(devices_router)
app.include_router(telemetry_router)
app.include_router(control_router)
app.include_router(personnel_router)
app.include_router(policy_router)
app.include_router(iot_policy_router)
app.include_router(security_router)
app.include_router(response_router)
app.include_router(events_router)
app.include_router(access_router)
app.include_router(simulation_router)
app.include_router(attack_router)
