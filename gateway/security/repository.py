"""Store security events and limit repeated observation rows."""

from datetime import datetime, timezone
import time
from threading import Lock

from gateway.database import get_connection

SECURITY_OBSERVATION_LOG_COOLDOWN_SECONDS = 5
_recent_policy_events: dict[tuple[str, str], float] = {}
_recent_policy_events_lock = Lock()


def _should_persist_repeated_observation(
    device_id: str, event_type: str, reason: str
) -> bool:
    """Rate-limit identical operator-facing violation rows without changing detector counts."""
    now = time.monotonic()
    key = (device_id, event_type, reason)
    with _recent_policy_events_lock:
        previous = _recent_policy_events.get(key)
        if (
            previous is not None
            and now - previous < SECURITY_OBSERVATION_LOG_COOLDOWN_SECONDS
        ):
            return False
        _recent_policy_events[key] = now
        return True


def clear_security_event_cooldowns() -> None:
    """Clear in-memory log cooldown state after a demo reset."""
    with _recent_policy_events_lock:
        _recent_policy_events.clear()


def add_security_event(
    device_id: str,
    event_type: str,
    reason: str,
    previous_state: str | None = None,
    new_state: str | None = None,
    message_count: int | None = None,
    violation_count: int | None = None,
):
    """Persist one security event; repeated identical policy violations are rate-limited."""
    if event_type in {
        "policy_violation",
        "integrity_disagreement",
        "integrity_recovery_observation",
        "monitoring_uncertainty",
    } and not _should_persist_repeated_observation(device_id, event_type, reason):
        return False

    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO security_events (
                timestamp, device_id, event_type, reason, previous_state, new_state,
                message_count, violation_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                device_id,
                event_type,
                reason,
                previous_state,
                new_state,
                message_count,
                violation_count,
            ),
        )
    return True
