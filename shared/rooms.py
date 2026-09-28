"""Room records and registration payloads."""

from pydantic import BaseModel


class Room(BaseModel):
    room_id: str
    name: str


class RoomRegistrationRequest(BaseModel):
    """Operator-supplied data for a new room; the gateway assigns room_id."""

    name: str


class RoomRegistrationPreview(BaseModel):
    """Shows the next room identity that the gateway would assign."""

    room_id: str
    name: str


class RoomUpdateRequest(BaseModel):
    """Editable room attributes. Stable room_id is intentionally excluded."""

    name: str
