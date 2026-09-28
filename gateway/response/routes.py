"""Response history for monitoring and evaluation."""

from fastapi import APIRouter, Query

from gateway.response.repository import list_responses

router = APIRouter(prefix="/responses", tags=["Responses"])


@router.get("")
def get_responses(
    device_id: str | None = None, limit: int = Query(default=100, ge=1, le=500)
):
    return list_responses(device_id=device_id, limit=limit)
