import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class UserStatus(StrEnum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


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

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        local_part, separator, domain = normalized.partition("@")
        local_pattern = r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+"
        domain_pattern = (
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
            r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
        )
        if (
            not separator
            or not re.fullmatch(local_pattern, local_part)
            or local_part.startswith(".")
            or local_part.endswith(".")
            or ".." in local_part
            or not re.fullmatch(domain_pattern, domain)
        ):
            raise ValueError("Format email pengguna tidak valid")
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Nama pengguna minimal 2 karakter")
        return normalized


class UserView(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    status: str
    division_code: str | None
    role: Role
    created_at: datetime


class UserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UserStatus
    reason: str = Field(min_length=8, max_length=500)


class RoleAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role
    division_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    valid_until: datetime | None = None
    reason: str = Field(min_length=8, max_length=500)


class RoleAssignmentView(BaseModel):
    assignment_id: UUID
    role: Role
    division_code: str | None
    valid_from: datetime
    valid_until: datetime | None
    reason: str
    created_at: datetime


class ProjectAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    valid_until: datetime | None = None
    reason: str = Field(min_length=8, max_length=500)


class ProjectAssignmentView(BaseModel):
    assignment_id: UUID
    project_id: UUID
    project_code: str
    project_name: str
    valid_from: datetime
    valid_until: datetime | None
    reason: str
    created_at: datetime


class UserDirectoryView(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    status: UserStatus
    roles: list[RoleAssignmentView]
    projects: list[ProjectAssignmentView]
    created_at: datetime
    updated_at: datetime


class UserDirectoryPage(BaseModel):
    items: list[UserDirectoryView]
    page: int
    page_size: int
    total: int
    pages: int
