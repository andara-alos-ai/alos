"""Typed inputs, context, accounting, and results for agentic execution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from alos.model_gateway import DataClassification
from alos.runtime.agentic.limits import ExecutionLimits


class ExecutionMode(StrEnum):
    TEST = "TEST"
    LIVE = "LIVE"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class StepType(StrEnum):
    MODEL = "MODEL"
    TOOL = "TOOL"
    DELEGATION = "DELEGATION"
    FINAL = "FINAL"


class ExecutionContext(BaseModel):
    """Immutable identity and scope carried through every execution step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    workspace_id: UUID
    division_id: UUID | None = None
    project_id: UUID | None = None
    tenant_id: UUID | None = None
    actor_user_id: UUID
    actor_role: str = Field(min_length=1, max_length=120)
    agent_id: UUID
    agent_version_id: UUID
    run_id: UUID
    correlation_id: UUID
    execution_mode: ExecutionMode
    classification: DataClassification
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class AgenticToolDefinition(BaseModel):
    """Tool metadata exposed to an engine; execution remains in ToolExecutor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_key: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    description: str = Field(min_length=1, max_length=2_000)
    input_schema: dict[str, Any]


class AgenticExecutionRequest(BaseModel):
    """Provider-neutral request passed from ``AgentRuntime`` to an engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context: ExecutionContext
    instructions: str = Field(min_length=1, max_length=50_000)
    input_text: str = Field(min_length=1, max_length=200_000)
    output_schema: dict[str, Any]
    tools: tuple[AgenticToolDefinition, ...] = ()
    limits: ExecutionLimits


class CumulativeUsage(BaseModel):
    """Accounting across every model, tool, retry, and delegated step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_model_calls: int = Field(default=0, ge=0)
    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_tool_calls: int = Field(default=0, ge=0)
    total_cost: Decimal = Field(default=Decimal("0"), ge=0)
    total_latency_milliseconds: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_token_total(self) -> CumulativeUsage:
        expected = self.total_input_tokens + self.total_output_tokens
        if self.total_tokens != expected:
            raise ValueError("total_tokens must equal input plus output tokens")
        return self


class AgenticStep(BaseModel):
    """Safe step metadata suitable for persistence and tracing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    step_type: StepType
    status: ExecutionStatus
    duration_milliseconds: int = Field(ge=0)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str | None = Field(default=None, min_length=1, max_length=80)
    tool_key: str | None = Field(default=None, min_length=1, max_length=200)
    error_code: str | None = Field(default=None, min_length=1, max_length=120)


class AgenticExecutionResult(BaseModel):
    """Terminal engine result with cumulative usage and no secret-bearing logs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    correlation_id: UUID
    status: ExecutionStatus
    output: dict[str, Any] | None = None
    usage: CumulativeUsage = Field(default_factory=CumulativeUsage)
    steps: tuple[AgenticStep, ...] = ()
    error_code: str | None = Field(default=None, min_length=1, max_length=120)
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> AgenticExecutionResult:
        if self.status == ExecutionStatus.SUCCEEDED and self.output is None:
            raise ValueError("successful execution requires output")
        if self.status != ExecutionStatus.SUCCEEDED and not self.error_code:
            raise ValueError("non-successful execution requires error_code")
        return self
