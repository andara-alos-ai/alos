from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)
    search: str | None = Field(default=None, min_length=2, max_length=120)
    status: str | None = Field(default=None, min_length=2, max_length=40)
    project_id: UUID | None = None
    sort_by: str = Field(default="created_at", min_length=2, max_length=40)
    sort_order: SortOrder = SortOrder.DESC

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page[ItemT](BaseModel):
    items: list[ItemT]
    page: int
    page_size: int
    total: int
    pages: int

    @classmethod
    def build(cls, items: list[ItemT], request: PageRequest, total: int) -> "Page[ItemT]":
        return cls(
            items=items,
            page=request.page,
            page_size=request.page_size,
            total=total,
            pages=ceil(total / request.page_size) if total else 0,
        )


class WorkItemRead(BaseModel):
    work_item_id: UUID
    project_id: UUID | None
    division_code: str
    title: str
    work_type: str
    priority: str
    status: str
    owner_user_id: UUID | None
    due_at: datetime | None
    correlation_id: UUID
    created_at: datetime
    updated_at: datetime


class LeadRead(BaseModel):
    lead_id: UUID
    project_id: UUID
    work_item_id: UUID
    workflow_run_id: UUID
    full_name: str
    phone: str | None
    email: str | None
    source: str
    consent_recorded: bool
    status: str
    assigned_user_id: UUID | None
    current_step: str
    workflow_status: str
    created_at: datetime
    updated_at: datetime


class SalesInteractionRead(BaseModel):
    interaction_id: UUID
    lead_id: UUID
    workflow_run_id: UUID
    actor_user_id: UUID
    channel: str
    outcome: str
    notes: str
    evidence_reference: str | None
    occurred_at: datetime


class BudgetRead(BaseModel):
    budget_id: UUID
    project_id: UUID
    code: str
    name: str
    currency: str
    allocated_amount: Decimal
    committed_amount: Decimal
    spent_amount: Decimal
    available_amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime


class PaymentRequestRead(BaseModel):
    payment_request_id: UUID
    project_id: UUID
    budget_id: UUID
    work_item_id: UUID
    workflow_run_id: UUID
    approval_request_id: UUID | None
    document_version_id: UUID
    requester_user_id: UUID
    payee_name: str
    purpose: str
    amount: Decimal
    currency: str
    requested_payment_date: date
    status: str
    budget_available: bool
    current_step: str
    workflow_status: str
    created_at: datetime
    updated_at: datetime


class SiteEvidenceRead(BaseModel):
    site_evidence_id: UUID
    project_id: UUID
    work_item_id: UUID
    workflow_run_id: UUID
    document_version_id: UUID
    submitted_by_user_id: UUID
    work_package_code: str
    claim_date: date
    claimed_progress: Decimal
    measured_progress: Decimal
    variance: Decimal
    status: str
    reviewer_user_id: UUID | None
    verified_progress: Decimal | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KpiSnapshotRead(BaseModel):
    kpi_snapshot_id: UUID
    project_id: UUID
    metric_code: str
    period_start: date
    period_end: date
    value: Decimal
    unit: str
    source_entity_type: str
    source_entity_id: UUID
    verification_status: str
    created_at: datetime


class LegalCaseRead(BaseModel):
    legal_case_id: UUID
    project_id: UUID
    work_item_id: UUID
    workflow_run_id: UUID
    document_version_id: UUID
    document_type: str
    reference_code: str
    title: str
    counterparty: str | None
    source_authority: str | None
    effective_date: date | None
    expiry_date: date | None
    status: str
    legal_status: str | None
    official_source_verified: bool
    reviewer_user_id: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RecruitmentRequestRead(BaseModel):
    recruitment_request_id: UUID
    project_id: UUID
    work_item_id: UUID
    workflow_run_id: UUID
    position_title: str
    requesting_division_code: str
    employment_type: str
    headcount: int
    justification: str
    criteria_version: str
    status: str
    reviewer_user_id: UUID | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PersonnelRequirementRead(BaseModel):
    requirement_code: str
    status: str


class PersonnelChecklistRead(BaseModel):
    personnel_checklist_id: UUID
    recruitment_request_id: UUID
    candidate_id: UUID
    status: str
    created_at: datetime
    requirements: list[PersonnelRequirementRead]


class DocumentRead(BaseModel):
    document_id: UUID
    project_id: UUID | None
    division_code: str | None
    logical_name: str
    classification: str
    document_version_id: UUID
    version_number: int
    original_filename: str | None
    sha256: str
    media_type: str
    size_bytes: int
    storage_provider: str
    scan_status: str
    verification_status: str
    created_at: datetime
    updated_at: datetime


class EvidenceRead(BaseModel):
    evidence_id: UUID
    work_item_id: UUID
    project_id: UUID | None
    division_code: str
    document_version_id: UUID | None
    claim_type: str
    status: str
    created_at: datetime


class ApprovalRead(BaseModel):
    approval_request_id: UUID
    work_item_id: UUID
    project_id: UUID | None
    division_code: str
    requester_user_id: UUID
    policy_code: str
    policy_version: str
    status: str
    material_fingerprint: str
    created_at: datetime
    decided_at: datetime | None
    approver_user_id: UUID | None
    decision_reason: str | None


class ExceptionRead(BaseModel):
    exception_id: UUID
    work_item_id: UUID | None
    project_id: UUID | None
    division_code: str | None
    category: str
    severity: str
    status: str
    owner_user_id: UUID | None
    due_at: datetime | None
    created_at: datetime


class CapaRead(BaseModel):
    capa_id: UUID
    exception_id: UUID
    work_item_id: UUID | None
    project_id: UUID | None
    division_code: str | None
    status: str
    root_cause: str | None
    corrective_action: str | None
    preventive_action: str | None
    reviewer_user_id: UUID | None
    due_at: datetime | None
    closed_at: datetime | None
    created_at: datetime


class ExecutiveBriefRead(BaseModel):
    executive_brief_id: UUID
    project_id: UUID | None
    workflow_run_id: UUID
    period_start: date
    period_end: date
    title: str
    narrative: str
    source_references: list[str]
    status: str
    reviewer_user_id: UUID | None
    review_notes: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunRead(BaseModel):
    workflow_run_id: UUID
    workflow_id: str
    workflow_version: str
    work_item_id: UUID | None
    project_id: UUID | None
    division_code: str | None
    current_step: str
    status: str
    correlation_id: UUID
    started_at: datetime
    completed_at: datetime | None


class TransitionEventRead(BaseModel):
    transition_event_id: UUID
    workflow_run_id: UUID
    from_step: str
    outcome: str
    to_step: str
    actor_type: str
    actor_id: str
    occurred_at: datetime


class AgentRunRead(BaseModel):
    agent_run_id: UUID
    agent_id: str
    agent_version: str
    workflow_run_id: UUID | None
    project_id: UUID | None
    status: str
    input_reference: dict[str, Any] | list[Any]
    output_reference: dict[str, Any] | list[Any] | None
    correlation_id: UUID
    started_at: datetime
    completed_at: datetime | None


class AuditEntryRead(BaseModel):
    audit_entry_id: UUID
    occurred_at: datetime
    actor_type: str
    actor_id: str
    active_role: str | None
    action: str
    entity_type: str
    entity_id: str
    reason: str | None
    before_masked: dict[str, Any] | None
    after_masked: dict[str, Any] | None
    correlation_id: UUID
    previous_hash: str | None
    entry_hash: str
