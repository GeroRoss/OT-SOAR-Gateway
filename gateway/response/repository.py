"""Store response outcomes and execution timings for audit and evaluation."""

import json
from datetime import datetime, timezone

from gateway.database import get_connection


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_response(
    *,
    device_id: str,
    room_id: str,
    device_type: str,
    criticality: str,
    trigger_reason: str,
    strategy: str,
    action: str,
    success: bool,
    outcome: str,
    safety_context: dict,
    started_at: str,
    completed_at: str,
    duration_ms: float,
) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO response_events (
                started_at,
                completed_at,
                device_id,
                room_id,
                device_type,
                criticality,
                trigger_reason,
                strategy,
                action,
                success,
                outcome,
                safety_context,
                duration_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                started_at,
                completed_at,
                device_id,
                room_id,
                device_type,
                criticality,
                trigger_reason,
                strategy,
                action,
                1 if success else 0,
                outcome,
                json.dumps(safety_context),
                duration_ms,
            ),
        )
        return cursor.lastrowid


def list_responses(device_id: str | None = None, limit: int = 100):
    with get_connection() as connection:
        if device_id:
            rows = connection.execute(
                """
                SELECT *
                FROM response_events
                WHERE device_id = ?
                ORDER BY response_id DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM response_events
                ORDER BY response_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["success"] = bool(item["success"])
        item["safety_context"] = json.loads(item["safety_context"] or "{}")
        results.append(item)
    return results
