from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkQueueScope(StrEnum):
    MINE = "mine"
    UNASSIGNED = "unassigned"
    DIVISION = "division"
    OVERDUE = "overdue"


class WorkAssignmentAction(StrEnum):
    CLAIM = "CLAIM"
    ASSIGN = "ASSIGN"
    DELEGATE = "DELEGATE"
    RELEASE = "RELEASE"


class WorkItemClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=8, max_length=500)


class WorkItemDelegate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_user_id: UUID
    reason: str = Field(min_length=8, max_length=500)


class WorkItemDeadlineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    due_at: datetime
    reason: str = Field(min_length=8, max_length=500)

    @field_validator("due_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Deadline wajib menyertakan zona waktu")
        return value


class WorkItemOperationalView(BaseModel):
    work_item_id: UUID
    organization_id: UUID
    project_id: UUID | None
    division_code: str
    title: str
    work_type: str
    priority: str
    status: str
    owner_user_id: UUID | None
    claimed_at: datetime | None
    due_at: datetime | None
    overdue: bool
    escalation_level: int
    escalated_at: datetime | None
    correlation_id: UUID
    created_at: datetime
    updated_at: datetime


class ApprovalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=8, max_length=500)


class ApprovalOperationalView(BaseModel):
    approval_request_id: UUID
    work_item_id: UUID
    requester_user_id: UUID
    assigned_approver_user_id: UUID | None
    status: str
    due_at: datetime | None
    claimed_at: datetime | None
    escalation_level: int


class DeadlineEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_minutes: int = Field(default=1440, ge=1, le=10080)
    escalation_interval_minutes: int = Field(default=60, ge=15, le=1440)


class DeadlineEvaluationResult(BaseModel):
    evaluated_at: datetime
    work_items_due_soon: int
    work_items_overdue: int
    approvals_due_soon: int
    approvals_overdue: int
    reminders_created: int


class ReminderView(BaseModel):
    reminder_id: UUID
    work_item_id: UUID | None
    approval_request_id: UUID | None
    recipient_user_id: UUID | None
    division_code: str | None
    reminder_type: str
    escalation_level: int
    status: str
    scheduled_for: datetime
    created_at: datetime


class ExceptionStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    CAPA_REQUIRED = "CAPA_REQUIRED"
    RESOLVED = "RESOLVED"


class ExceptionTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: ExceptionStatus
    reason: str = Field(min_length=8, max_length=2000)
    resolution_document_version_id: UUID | None = None

    @model_validator(mode="after")
    def require_resolution_evidence(self) -> "ExceptionTransition":
        if self.target_status == ExceptionStatus.RESOLVED:
            if self.resolution_document_version_id is None:
                raise ValueError("Penyelesaian exception wajib memiliki evidence dokumen")
        elif self.resolution_document_version_id is not None:
            raise ValueError("Evidence penyelesaian hanya untuk status RESOLVED")
        return self


class ExceptionOperationalView(BaseModel):
    exception_id: UUID
    status: str
    owner_user_id: UUID | None
    resolution_reason: str | None
    resolution_document_version_id: UUID | None
    resolved_at: datetime | None
    updated_at: datetime


class CapaAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_user_id: UUID
    reason: str = Field(min_length=8, max_length=500)


class CapaStatus(StrEnum):
    OPEN = "OPEN"
    ANALYSIS = "ANALYSIS"
    ACTION_IN_PROGRESS = "ACTION_IN_PROGRESS"
    VERIFICATION = "VERIFICATION"
    CLOSED = "CLOSED"


class CapaTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: CapaStatus
    reason: str = Field(min_length=8, max_length=2000)
    verification_notes: str | None = Field(default=None, min_length=8, max_length=2000)
    evidence_document_version_id: UUID | None = None

    @model_validator(mode="after")
    def require_closure_evidence(self) -> "CapaTransition":
        if self.target_status == CapaStatus.CLOSED:
            if self.verification_notes is None or self.evidence_document_version_id is None:
                raise ValueError("Penutupan CAPA wajib memiliki catatan dan evidence verifikasi")
        elif self.verification_notes is not None or self.evidence_document_version_id is not None:
            raise ValueError("Evidence verifikasi hanya untuk penutupan CAPA")
        return self


class CapaOperationalView(BaseModel):
    capa_id: UUID
    exception_id: UUID
    status: str
    owner_user_id: UUID | None
    reviewer_user_id: UUID | None
    verification_notes: str | None
    evidence_document_version_id: UUID | None
    closed_at: datetime | None
    updated_at: datetime
