"""Store management and control activity with optional event metadata."""

import json
from datetime import datetime, timezone

from gateway.database import get_connection


def add_activity_event(
    event_type: str,
    message: str,
    source_id: str | None = None,
    room_id: str | None = None,
    actor_id: str | None = None,
    actor_name: str | None = None,
    actor_clearance: int | None = None,
    metadata: dict | None = None,
):
    """Store an activity/audit record while preserving optional structured evidence."""

    timestamp = datetime.now(timezone.utc).isoformat()
    metadata_json = json.dumps(metadata, separators=(",", ":")) if metadata else None

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO activity_events (
                timestamp,
                event_type,
                source_id,
                room_id,
                actor_id,
                actor_name,
                actor_clearance,
                message,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                event_type,
                source_id,
                room_id,
                actor_id,
                actor_name,
                actor_clearance,
                message,
                metadata_json,
            ),
        )

    return cursor.lastrowid
