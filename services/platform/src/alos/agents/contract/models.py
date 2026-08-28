from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    TESTED = "TESTED"
    REVIEWED = "REVIEWED"
    STAGED = "STAGED"
    RELEASED = "RELEASED"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class AgentDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    agent_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    name: str = Field(min_length=3, max_length=120)
    domain: str = Field(min_length=2, max_length=64)
    purpose: str = Field(min_length=20)
    human_owner: str = Field(min_length=3)
    triggers: list[str] = Field(min_length=1)
    inputs: list[str] = Field(min_length=1)
    source_of_truth: list[str] = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)
    outputs: list[str] = Field(min_length=1)
    tools_allowed: list[str]
    approval_boundary: list[str] = Field(min_length=1)
    evidence_requirement: list[str] = Field(min_length=1)
    forbidden_actions: list[str] = Field(min_length=1)
    metrics: list[str] = Field(alias="KPI/metrics", min_length=1)
    escalation: list[str] = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: AgentStatus

    @field_validator(
        "triggers",
        "inputs",
        "source_of_truth",
        "capabilities",
        "outputs",
        "tools_allowed",
        "approval_boundary",
        "evidence_requirement",
        "forbidden_actions",
        "metrics",
        "escalation",
    )
    @classmethod
    def reject_blank_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("daftar tidak boleh memuat nilai kosong")
        return values
