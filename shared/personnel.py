"""Personnel accounts and account-management request models."""

from enum import Enum
from pydantic import BaseModel, Field


class PersonnelRole(str, Enum):
    VISITOR = "visitor"
    CONTRACTOR = "contractor"
    TECHNICIAN = "technician"
    FACILITY_OPERATOR = "facility_operator"
    FACILITY_ENGINEER = "facility_engineer"
    SECURITY_OPERATOR = "security_operator"
    OT_ADMINISTRATOR = "ot_administrator"


class Personnel(BaseModel):
    person_id: str
    name: str
    role: PersonnelRole
    clearance: int = Field(ge=0, le=5)
    authorized_rooms: list[str] = Field(default_factory=list)
    active: bool = True


class PersonnelRegistrationRequest(BaseModel):
    """Input for a new personnel record; person_id is gateway-generated."""

    name: str
    role: PersonnelRole
    clearance: int = Field(ge=0, le=5)
    authorized_rooms: list[str] = Field(default_factory=list)
    active: bool = True


class PersonnelUpdateRequest(BaseModel):
    """Editable personnel authorization attributes; person_id is immutable."""

    name: str
    role: PersonnelRole
    clearance: int = Field(ge=0, le=5)
    authorized_rooms: list[str] = Field(default_factory=list)
    active: bool = True


class PersonnelRegistrationPreview(BaseModel):
    person_id: str
