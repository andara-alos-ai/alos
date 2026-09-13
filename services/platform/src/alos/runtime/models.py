"""Public runtime request/response models and shared status types."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from alos.tools.executor import StructuredToolCall

RunStatus = Literal[
    "SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED", "CANCEL_REQUESTED"
]


class AgentRunRequest(BaseModel):
    """A human-requested, bounded runtime invocation."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_id: UUID | None = None
    project_id: UUID | None = None
    tenant_id: UUID | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    requested_tool_keys: list[str] = Field(default_factory=list)
    tool_calls: list[StructuredToolCall] = Field(default_factory=list, max_length=20)
    testing: bool = False


class WorkspaceBudgetRequest(BaseModel):
    """Human-controlled daily policy; it is never selected by an LLM."""

    model_config = ConfigDict(extra="forbid")

    daily_request_limit: int = Field(ge=1, le=100_000)
    daily_output_token_limit: int = Field(ge=1_000, le=10_000_000)
    daily_cost_cap_usd: Decimal = Field(ge=0, le=1_000_000)


class WorkspaceBudget(BaseModel):
    workspace_id: UUID
    daily_request_limit: int
    daily_output_token_limit: int
    daily_cost_cap_usd: Decimal


class ToolDecision(BaseModel):
    tool_key: str
    decision: Literal["ALLOWED", "BLOCKED"]
    reason: str


class AgentRunResult(BaseModel):
    agent_run_id: UUID
    agent_key: str
    semantic_version: str
    status: RunStatus
    correlation_id: UUID
    output: dict[str, Any] | None = None
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_milliseconds: int | None = None
    estimated_cost_usd: Decimal | None = None
    total_model_calls: int = Field(default=1, ge=0)
    total_tool_calls: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    tool_decisions: list[ToolDecision] = Field(default_factory=list)
    error_code: str | None = None


class AgentRunSummary(BaseModel):
    """Safe run metadata for operations views; it never exposes inputs or output bodies."""

    agent_run_id: UUID
    agent_key: str
    semantic_version: str
    status: RunStatus
    correlation_id: UUID
    created_at: datetime
    completed_at: datetime | None
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_milliseconds: int | None
    estimated_cost_usd: Decimal | None
    error_code: str | None = None
    block_reason: str | None = None


class WorkspaceUsageSummary(BaseModel):
    workspace_id: UUID
    request_count: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
