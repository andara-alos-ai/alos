from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field



class DivisionCode(StrEnum):
    FINANCE = "FINANCE"
    SALES_MARKETING = "SALES_MARKETING"
    PROPERTY = "PROPERTY"
    HR = "HR"
    LEGAL = "LEGAL"
    IT = "IT"


class HumanRole(StrEnum):
    DIRECTOR = "DIRECTOR"
    DIVISION_LEAD = "DIVISION_LEAD"
    DIVISION_MEMBER = "DIVISION_MEMBER"
    IT_ADMIN = "IT_ADMIN"
    AI_ADMIN = "AI_ADMIN"
    # Legacy values remain readable while existing deployments migrate assignments.
    DIVISION_OWNER = "DIVISION_OWNER"
    IT_LEAD = "IT_LEAD"
    TECHNICAL_REVIEWER = "TECHNICAL_REVIEWER"
    BUSINESS_REVIEWER = "BUSINESS_REVIEWER"
    QA_SECURITY = "QA_SECURITY"


class DataScope(StrEnum):
    COMPANY = "COMPANY"
    DIVISION = "DIVISION"
    PROJECT = "PROJECT"
    OWN_ASSIGNED = "OWN_ASSIGNED"


class SystemActor(StrEnum):
    GENESIS = "GENESIS"


class SourceRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_key: str
    evidence_refs: list[str]
    max_tokens: int | None = None


class ContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    lifecycle_status: str
    owner_user_id: UUID
    risk_level: str
    scope: DataScope
    tools: list[str]
    permissions: list[str]
    sources: list[SourceRequirement] = Field(default_factory=list)
    budget_usd: float | None = None
    token_limit: int | None = None
