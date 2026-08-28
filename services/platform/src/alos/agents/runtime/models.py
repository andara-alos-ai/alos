from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    capability: str
    input_references: list[str] = Field(min_length=1)
    requested_tools: list[str] = Field(default_factory=list)
    material_action: bool = False
    correlation_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)


class AgentExecutionPlan(BaseModel):
    run_id: UUID
    agent_id: str
    agent_version: str
    capability: str
    approved_tools: list[str]
    input_references: list[str]
    status: AgentRunStatus
    requires_human_review: bool
    correlation_id: UUID
    idempotency_key: str
