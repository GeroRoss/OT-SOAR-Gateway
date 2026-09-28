"""Gateway health checks and the development demo reset endpoint."""

import httpx
from fastapi import APIRouter, HTTPException

from gateway.system.reset import reset_demo_to_seeded_state

router = APIRouter(tags=["System"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/system/reset-demo-data")
async def reset_demo_data():
    """Development-only destructive reset back to predefined seeded records."""

    try:
        return await reset_demo_to_seeded_state()
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The demo reset could not establish a clean gateway/facility "
                f"runtime boundary: {exc}"
            ),
        ) from exc
