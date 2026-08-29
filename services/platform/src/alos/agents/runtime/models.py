from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alos.agents.contract import AgentDefinition, AgentKind, CapabilityExecutionMode
from alos.tools import ToolReference


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

    agent_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    agent_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    capability: str
    execution_mode: CapabilityExecutionMode = CapabilityExecutionMode.DETERMINISTIC
    input_references: list[str] = Field(min_length=1)
    requested_tools: list[str] = Field(default_factory=list)
    material_action: bool = False
    correlation_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    workflow_id: str | None = Field(default=None, pattern=r"^FLOW-00[1-6]$")
    workflow_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    workflow_step_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]+$")

    @field_validator("agent_id", mode="before")
    @classmethod
    def normalize_agent_id(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("input_references", "requested_tools")
    @classmethod
    def reject_blank_or_duplicate_lists(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError("daftar runtime tidak boleh kosong atau memiliki spasi di tepi")
        if len(values) != len(set(values)):
            raise ValueError("daftar runtime tidak boleh memuat nilai duplikat")
        return values


class AgentExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    agent_id: str
    agent_version: str
    contract_version: str
    agent_kind: AgentKind
    contract_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    contract_snapshot: AgentDefinition
    capability: str
    execution_mode: CapabilityExecutionMode
    approved_tools: tuple[str, ...]
    approved_tool_releases: tuple[ToolReference, ...]
    input_references: tuple[str, ...]
    status: AgentRunStatus
    requires_human_review: bool
    correlation_id: UUID
    idempotency_key: str
    workflow_id: str | None
    workflow_version: str | None
    workflow_step_id: str | None


class CapabilityHandlerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output_reference: dict[str, object]
    evidence_references: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class CapabilityDispatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    agent_id: str
    agent_version: str
    capability: str
    handler_id: str
    status: AgentRunStatus
    output_reference: dict[str, object]
    evidence_references: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_human_review: bool

    @classmethod
    def from_handler(
        cls,
        plan: AgentExecutionPlan,
        handler_id: str,
        output: CapabilityHandlerOutput,
    ) -> "CapabilityDispatchResult":
        requires_review = plan.requires_human_review or bool(output.warnings)
        return cls(
            run_id=plan.run_id,
            agent_id=plan.agent_id,
            agent_version=plan.agent_version,
            capability=plan.capability,
            handler_id=handler_id,
            status=(
                AgentRunStatus.NEEDS_REVIEW
                if requires_review
                else AgentRunStatus.COMPLETED
            ),
            output_reference=output.output_reference,
            evidence_references=output.evidence_references,
            warnings=output.warnings,
            requires_human_review=requires_review,
        )
