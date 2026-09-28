"""HTTP telemetry ingestion, latest readings, and recorded history."""

from fastapi import APIRouter, HTTPException, Query
from gateway.registry import get_device
from gateway.telemetry.service import ingest_environmental, ingest_pdu, ingest_smoke
from gateway.telemetry.store import (
    environmental_telemetry,
    get_history,
    pdu_telemetry,
    smoke_telemetry,
)
from shared.devices import Protocol
from shared.telemetry import EnvironmentalTelemetry, PDUTelemetry, SmokeTelemetry

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


@router.post("/environmental", status_code=202)
def receive_environmental_telemetry(telemetry: EnvironmentalTelemetry):
    return ingest_environmental(telemetry, Protocol.HTTP)


@router.get("/environmental/{device_id}")
def get_environmental_telemetry(device_id: str):
    telemetry = environmental_telemetry.get(device_id)
    if telemetry is None:
        history = get_history(device_id, 1)
        if history and history[-1]["telemetry_type"] == "environmental":
            item = history[-1]
            return EnvironmentalTelemetry(
                device_id=device_id,
                room_id=item["room_id"],
                temperature=item["temperature"],
                humidity=item["humidity"],
            )
        raise HTTPException(status_code=404, detail="No environmental telemetry found")
    return telemetry


@router.post("/smoke", status_code=202)
def receive_smoke_telemetry(telemetry: SmokeTelemetry):
    return ingest_smoke(telemetry, Protocol.HTTP)


@router.get("/smoke/{device_id}")
def get_smoke_telemetry(device_id: str):
    telemetry = smoke_telemetry.get(device_id)
    if telemetry is None:
        raise HTTPException(status_code=404, detail="No smoke telemetry found")
    return telemetry


@router.post("/pdu", status_code=202)
def receive_pdu_telemetry(telemetry: PDUTelemetry):
    return ingest_pdu(telemetry, Protocol.HTTP)


@router.get("/pdu/{device_id}")
def get_pdu_telemetry(device_id: str):
    telemetry = pdu_telemetry.get(device_id)
    if telemetry is None:
        raise HTTPException(status_code=404, detail="No PDU telemetry found")
    return telemetry


@router.get("/history/{device_id}")
def telemetry_history(device_id: str, limit: int = Query(default=120, ge=1, le=1000)):
    if get_device(device_id) is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return get_history(device_id, limit)
