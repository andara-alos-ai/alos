"""Typed API and tool boundaries for canonical ALOS operating data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alos.identity import DivisionCode

Classification = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
TaskStatus = Literal["DRAFT", "TODO", "IN_PROGRESS", "IN_REVIEW", "DONE", "CANCELLED"]


class Page(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_code: DivisionCode
    project_id: UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10_000)
    status: Literal["DRAFT", "TODO"] = "TODO"
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    due_date: date | None = None
    assignee_user_id: UUID | None = None
    owner_user_id: UUID | None = None
    evidence_required: bool = False
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)


class TaskStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus


class TaskRecord(BaseModel):
    task_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID
    division_code: DivisionCode
    project_id: UUID | None
    project_name: str | None
    title: str
    description: str
    status: TaskStatus
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    due_date: date | None
    assignee_user_id: UUID | None
    owner_user_id: UUID
    created_by_user_id: UUID | None
    created_by_actor_kind: Literal["HUMAN", "GENESIS", "AGENT"]
    evidence_required: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskList(BaseModel):
    items: list[TaskRecord]
    pagination: Page


class EvidenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_code: DivisionCode
    project_id: UUID | None = None
    task_id: UUID | None = None
    document_id: UUID | None = None
    object_key: str | None = Field(default=None, max_length=500)
    classification: Classification = "INTERNAL"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_relations(self) -> EvidenceCreateRequest:
        if self.task_id is None and self.project_id is None:
            raise ValueError("task_id or project_id is required")
        if self.document_id is None and not self.object_key:
            raise ValueError("document_id or object_key is required")
        return self


class EvidenceRecord(BaseModel):
    evidence_id: UUID
    workspace_id: UUID
    division_code: DivisionCode
    project_id: UUID | None
    task_id: UUID | None
    owner_user_id: UUID
    uploaded_by_user_id: UUID
    document_id: UUID | None
    object_key: str | None
    classification: Classification
    validation_status: Literal["PENDING", "VALID", "INVALID", "WAIVED"]
    version: int
    metadata: dict[str, Any]
    created_at: datetime


class FindingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_code: DivisionCode | None = None
    project_id: UUID | None = None
    source_kind: Literal["DOCUMENT", "TASK", "EVIDENCE", "PROJECT", "GENESIS", "AGENT", "EXTERNAL"]
    source_id: UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=2, max_length=20_000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    recommendation: str = Field(default="", max_length=10_000)
    citation_refs: list[dict[str, Any]] = Field(default_factory=list)
    owner_user_id: UUID | None = None
    due_date: date | None = None


class FindingStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["OPEN", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "DISMISSED"]
    resolution: str | None = Field(default=None, max_length=10_000)


class FindingRecord(BaseModel):
    finding_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID | None
    division_code: DivisionCode | None
    project_id: UUID | None
    source_kind: str
    source_id: UUID | None
    title: str
    description: str
    severity: str
    status: str
    owner_user_id: UUID | None
    recommendation: str
    citation_refs: list[dict[str, Any]]
    generated_by: Literal["HUMAN", "GENESIS", "AGENT"]
    resolution: str | None
    due_date: date | None
    created_at: datetime
    updated_at: datetime


class ApprovalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_code: DivisionCode | None = None
    project_id: UUID | None = None
    approval_kind: Literal["BUSINESS", "DOCUMENT", "AGENT", "PROPOSED_ACTION", "REPORT"]
    subject_type: str = Field(min_length=2, max_length=80)
    subject_id: UUID
    payload_digest: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10_000)
    urgency: Literal["NORMAL", "URGENT"] = "NORMAL"


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVED", "REJECTED"]
    payload_digest: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    notes: str = Field(min_length=2, max_length=5_000)


class ApprovalRecord(BaseModel):
    approval_request_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID | None
    division_code: DivisionCode | None
    project_id: UUID | None
    approval_kind: str
    subject_type: str
    subject_id: UUID
    payload_digest: str
    title: str
    description: str
    urgency: str
    status: str
    requested_by_user_id: UUID | None
    approver_user_id: UUID | None
    decision_notes: str | None
    requested_at: datetime
    decided_at: datetime | None


class ProposedActionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_code: DivisionCode | None = None
    project_id: UUID | None = None
    action_type: Literal["TASK_CREATE", "FINDING_CREATE"]
    payload: dict[str, Any]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10_000)
    urgency: Literal["NORMAL", "URGENT"] = "NORMAL"
    idempotency_key: str = Field(min_length=8, max_length=200)


class ProposedActionExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_digest: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class ProposedActionRecord(BaseModel):
    proposed_action_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID | None
    division_code: DivisionCode | None
    project_id: UUID | None
    action_type: str
    payload: dict[str, Any]
    payload_digest: str
    risk_level: str
    status: str
    requested_by_user_id: UUID | None
    requested_by_agent_version_id: UUID | None
    created_at: datetime
    executed_at: datetime | None
    idempotency_key: str | None
    approval_request_id: UUID | None = None
    approval_status: str | None = None
    executed_entity_type: str | None = None
    executed_entity_id: UUID | None = None


class ReportDefinitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_code: DivisionCode | None = None
    project_id: UUID | None = None
    name: str = Field(min_length=2, max_length=160)
    template_key: str = Field(default="EXECUTIVE_SUMMARY", min_length=2, max_length=80)
    scope: Literal["COMPANY", "DIVISION", "PROJECT", "OWN_ASSIGNED"]
    period: str = Field(default="ON_DEMAND", min_length=2, max_length=80)
    sections: list[str] = Field(default_factory=list, max_length=30)
    data_sources: list[str] = Field(default_factory=list, max_length=30)
    review_required: bool = True
    recipient_user_ids: list[UUID] = Field(default_factory=list)


class ReportScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_expression: str = Field(min_length=3, max_length=120)
    timezone: str = Field(default="Asia/Jakarta", min_length=3, max_length=80)
    next_run_at: datetime | None = None
    confirm: bool = False


class ReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=200)


class ReportDefinitionRecord(BaseModel):
    report_definition_id: UUID
    workspace_id: UUID
    division_id: UUID | None
    division_code: DivisionCode | None
    project_id: UUID | None
    name: str
    template_key: str
    scope: str
    period: str
    sections: list[Any]
    data_sources: list[Any]
    status: str
    review_required: bool
    recipient_user_ids: list[UUID]
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime
    schedule_expression: str | None = None
    timezone: str | None = None
    next_run_at: datetime | None = None


class ReportRecord(BaseModel):
    report_id: UUID
    report_definition_id: UUID
    organization_id: UUID
    workspace_id: UUID
    status: str
    content: dict[str, Any]
    provenance: list[dict[str, Any]]
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class BusinessRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    project_id: UUID | None = None
    record_type: str = Field(min_length=2, max_length=80)
    record_key: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=2, max_length=200)
    classification: Classification = "INTERNAL"
    payload: dict[str, Any] = Field(default_factory=dict)
    effective_date: date | None = None
    expires_at: datetime | None = None


class BusinessRecord(BaseModel):
    business_record_id: UUID
    workspace_id: UUID
    division_code: DivisionCode
    project_id: UUID | None
    domain: DivisionCode
    record_type: str
    record_key: str
    title: str
    status: str
    classification: Classification
    payload: dict[str, Any]
    effective_date: date | None
    expires_at: datetime | None
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime


class SearchResult(BaseModel):
    entity_type: Literal["DIVISION", "PROJECT", "TASK", "DOCUMENT", "REPORT", "FINDING", "AGENT"]
    entity_id: UUID
    title: str
    subtitle: str
    href: str
    division_code: DivisionCode | None = None
    updated_at: datetime


class OperationalDashboard(BaseModel):
    generated_at: datetime
    scope: str
    metrics: dict[str, int]
    tasks: list[TaskRecord]
    findings: list[FindingRecord]
    approvals: list[ApprovalRecord]
    reports: list[ReportRecord]
