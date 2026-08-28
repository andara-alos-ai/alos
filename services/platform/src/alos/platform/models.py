from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    CLOSED = "CLOSED"


class WorkItemPriority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class WorkItemStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,31}$")
    name: str = Field(min_length=3, max_length=160)


class ProjectView(BaseModel):
    project_id: UUID
    organization_id: UUID
    code: str
    name: str
    status: ProjectStatus
    created_at: datetime


class LeadIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, min_length=8, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    source: str = Field(min_length=2, max_length=80)
    consent_recorded: bool
    priority: WorkItemPriority = WorkItemPriority.NORMAL

    @model_validator(mode="after")
    def require_contact_channel(self) -> "LeadIntake":
        if not self.phone and not self.email:
            raise ValueError("Lead wajib memiliki telepon atau email")
        return self


class LeadIntakeResult(BaseModel):
    lead_id: UUID
    work_item_id: UUID
    workflow_run_id: UUID
    current_step: str
    work_item_status: WorkItemStatus
    due_at: datetime
    correlation_id: UUID


class WorkItemView(BaseModel):
    work_item_id: UUID
    organization_id: UUID
    project_id: UUID | None
    division_code: str
    title: str
    work_type: str
    priority: WorkItemPriority
    status: WorkItemStatus
    owner_user_id: UUID | None
    due_at: datetime | None
    correlation_id: UUID
    created_at: datetime


class SalesAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_pic_user_id: UUID


class InteractionOutcome(StrEnum):
    QUALIFIED = "qualified"
    RESERVED = "reserved"
    FOLLOW_UP = "follow_up"
    EXCEPTION = "exception"


class SalesInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: InteractionOutcome
    channel: str = Field(min_length=2, max_length=40)
    notes: str = Field(min_length=3, max_length=2000)
    evidence_reference: str | None = Field(default=None, max_length=500)
    reservation_reference: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def require_reservation_reference(self) -> "SalesInteraction":
        if self.outcome == InteractionOutcome.RESERVED and not self.reservation_reference:
            raise ValueError("Referensi reservasi wajib untuk outcome reserved")
        if self.outcome != InteractionOutcome.RESERVED and self.reservation_reference:
            raise ValueError("Referensi reservasi hanya boleh digunakan untuk outcome reserved")
        return self


class WorkflowActionResult(BaseModel):
    workflow_run_id: UUID
    work_item_id: UUID
    lead_id: UUID
    current_step: str
    workflow_status: str
    work_item_status: WorkItemStatus
    owner_user_id: UUID | None
    due_at: datetime | None
    terminal: bool
    correlation_id: UUID
