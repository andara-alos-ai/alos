from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    DIRECTOR = "DIRECTOR"
    AI_EXECUTIVE = "AI_EXECUTIVE"
    DIVISION_HEAD = "DIVISION_HEAD"
    SALES = "SALES"
    FINANCE = "FINANCE"
    PROPERTY = "PROPERTY"
    HR = "HR"
    LEGAL = "LEGAL"
    IT_ADMIN = "IT_ADMIN"
    AUDITOR = "AUDITOR"


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    organization_id: UUID
    roles: frozenset[Role] = Field(min_length=1)
    division_codes: frozenset[str] = Field(default_factory=frozenset)
    project_ids: frozenset[UUID] = Field(default_factory=frozenset)

    def has_any_role(self, *roles: Role) -> bool:
        return bool(self.roles.intersection(roles))

    def can_access_project(self, project_id: UUID) -> bool:
        organization_wide = self.has_any_role(
            Role.DIRECTOR,
            Role.AI_EXECUTIVE,
            Role.IT_ADMIN,
            Role.AUDITOR,
        )
        return organization_wide or project_id in self.project_ids


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=254)
    display_name: str = Field(min_length=2, max_length=160)
    division_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    role: Role


class UserView(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    status: str
    division_code: str | None
    role: Role
    created_at: datetime
