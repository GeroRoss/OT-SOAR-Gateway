"""Filtered event history for the dashboard."""

from fastapi import APIRouter, Query

from gateway.events.repository import list_normalized_events

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("")
def get_events(
    type: list[str] | None = Query(default=None),
    source_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    return list_normalized_events(types=type, source_id=source_id, limit=limit)
