"""Build the Action and Cause text used in management event logs.

Callers supply entity IDs, names, and changed fields; these helpers handle
labels and sentence assembly."""

from enum import Enum
from typing import Any, Callable

_ACRONYMS = {
    "abac": "ABAC",
    "hvac": "HVAC",
    "iot": "IoT",
    "ot": "OT",
    "pdu": "PDU",
    "id": "ID",
}


def humanize(value: Any) -> str:
    """Turn enum/raw identifiers into operator-facing text."""

    if isinstance(value, Enum):
        value = value.value

    if value is None:
        return "—"

    if isinstance(value, bool):
        return "Enabled" if value else "Disabled"

    text = str(value).replace("_", " ").strip()

    return " ".join(
        _ACRONYMS.get(word.lower(), word.capitalize()) for word in text.split()
    )


def entity_text(entity_type: str, entity_id: str, name: str | None = None) -> str:
    """Build a stable entity label containing its type and identifier."""

    base = f"{entity_type} {entity_id}".strip()

    if name and name.strip() and name.strip() != entity_id:
        return f"{base} ({name.strip()})"

    return base


def action_text(
    verb: str, entity_type: str, entity_id: str, name: str | None = None
) -> str:
    """Compose an Action-column phrase from reusable components."""

    return f"{verb} " f"{entity_text(entity_type, entity_id, name)}"


def changed_fields(
    before: Any,
    after: Any,
    fields: list[str],
    *,
    labels: dict[str, str] | None = None,
    formatters: dict[str, Callable[[Any], str]] | None = None,
) -> list[str]:
    """Describe fields whose values changed between two objects."""

    labels = labels or {}
    formatters = formatters or {}

    changes: list[str] = []

    for field in fields:
        old = getattr(before, field)
        new = getattr(after, field)

        if old == new:
            continue

        formatter = formatters.get(field, humanize)

        label = labels.get(field, humanize(field))

        changes.append(f"{label} changed from " f"{formatter(old)} to {formatter(new)}")

    return changes


def management_change(
    *,
    entity_type: str,
    entity_id: str,
    name: str | None,
    before: Any,
    after: Any,
    fields: list[str],
    labels: dict[str, str] | None = None,
    formatters: dict[str, Callable[[Any], str]] | None = None,
) -> tuple[str, str]:
    """Choose Enable/Disable for a status-only change, otherwise Update."""

    changes = changed_fields(
        before, after, fields, labels=labels, formatters=formatters
    )

    changed_names = [
        field for field in fields if getattr(before, field) != getattr(after, field)
    ]

    if changed_names == ["enabled"]:
        verb = "Enable" if after.enabled else "Disable"

        cause = "Manual Intervention"

        return (action_text(verb, entity_type, entity_id, name), cause)

    cause = "; ".join(changes) if changes else "No changes"

    return (action_text("Update", entity_type, entity_id, name), cause)
