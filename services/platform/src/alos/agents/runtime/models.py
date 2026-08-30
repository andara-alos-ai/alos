import json
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class CapabilityVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PROVISIONAL = "PROVISIONAL"
    UNVERIFIED = "UNVERIFIED"


class CapabilityExecutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    handler_id: str
    status: AgentRunStatus
    output_reference: dict[str, object]
    evidence_references: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    verification_status: CapabilityVerificationStatus
    provider_metadata: dict[str, object] = Field(default_factory=dict)


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
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    capability_contract_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
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
    execution: CapabilityExecutionRecord | None = None


class CapabilityHandlerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output_reference: dict[str, object]
    evidence_references: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    verification_status: CapabilityVerificationStatus = CapabilityVerificationStatus.VERIFIED
    provider_metadata: dict[str, object] = Field(default_factory=dict)


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
    verification_status: CapabilityVerificationStatus
    provider_metadata: dict[str, object]

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
            verification_status=output.verification_status,
            provider_metadata=output.provider_metadata,
        )

    def to_execution_record(self) -> CapabilityExecutionRecord:
        return CapabilityExecutionRecord(
            handler_id=self.handler_id,
            status=self.status,
            output_reference=self.output_reference,
            evidence_references=self.evidence_references,
            warnings=self.warnings,
            verification_status=self.verification_status,
            provider_metadata=self.provider_metadata,
        )


class AgentCapabilityExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    agent_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    capability: str = Field(pattern=r"^[a-z][a-z0-9_]{2,127}$")
    project_id: UUID | None = None
    input_references: list[str] = Field(min_length=1, max_length=20)
    requested_tools: list[str] = Field(default_factory=list, max_length=10)
    input_payload: dict[str, Any]
    data_classification: str = Field(
        default="INTERNAL", pattern=r"^(PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED)$"
    )

    @field_validator("input_references", "requested_tools")
    @classmethod
    def reject_duplicates(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Referensi atau tool tidak boleh duplikat")
        if any(not item.strip() or item != item.strip() for item in values):
            raise ValueError("Referensi atau tool tidak boleh kosong")
        return values

    @model_validator(mode="after")
    def reject_unsafe_payload(self) -> "AgentCapabilityExecuteRequest":
        encoded = json.dumps(
            self.input_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        if len(encoded) > 256 * 1024:
            raise ValueError("Payload agent melebihi batas 256 KiB")

        forbidden_keys = {
            "access_token",
            "api_key",
            "client_secret",
            "password",
            "passphrase",
            "private_key",
            "refresh_token",
            "secret",
        }

        def find_forbidden(value: object, path: str = "input_payload") -> str | None:
            if isinstance(value, dict):
                for key, child in value.items():
                    normalized = str(key).strip().lower().replace("-", "_")
                    child_path = f"{path}.{key}"
                    if normalized in forbidden_keys:
                        return child_path
                    finding = find_forbidden(child, child_path)
                    if finding is not None:
                        return finding
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    finding = find_forbidden(child, f"{path}[{index}]")
                    if finding is not None:
                        return finding
            return None

        forbidden_path = find_forbidden(self.input_payload)
        if forbidden_path is not None:
            raise ValueError(
                f"Kredensial tidak boleh dikirim melalui payload agent: {forbidden_path}"
            )
        return self


class AgentCapabilityExecutionView(BaseModel):
    run_id: UUID
    agent_id: str
    agent_version: str
    capability: str
    status: AgentRunStatus
    handler_id: str
    output_reference: dict[str, object]
    evidence_references: tuple[str, ...]
    warnings: tuple[str, ...]
    verification_status: CapabilityVerificationStatus
    requires_human_review: bool
    correlation_id: UUID
    production_effect: bool = False
