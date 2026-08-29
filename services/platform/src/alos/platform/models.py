from datetime import date, datetime
from decimal import Decimal
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


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None
    logical_name: str = Field(min_length=2, max_length=160)
    classification: str = Field(pattern=r"^(PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED)$")
    object_key: str = Field(min_length=3, max_length=500)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    media_type: str = Field(min_length=3, max_length=120)
    size_bytes: int = Field(ge=0)


class DocumentView(BaseModel):
    document_id: UUID
    document_version_id: UUID
    organization_id: UUID
    project_id: UUID | None
    logical_name: str
    classification: str
    version_number: int
    object_key: str
    sha256: str
    media_type: str
    size_bytes: int
    verification_status: str
    created_at: datetime


class StoredDocumentView(BaseModel):
    document_id: UUID
    document_version_id: UUID
    organization_id: UUID
    division_code: str | None
    project_id: UUID | None
    logical_name: str
    classification: str
    version_number: int
    original_filename: str
    sha256: str
    media_type: str
    size_bytes: int
    storage_provider: str
    scan_status: str
    verification_status: str
    created_at: datetime


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: UUID
    document_version_id: UUID
    claim_type: str = Field(min_length=2, max_length=120)


class EvidenceView(BaseModel):
    evidence_id: UUID
    work_item_id: UUID
    document_version_id: UUID
    claim_type: str
    status: str
    created_at: datetime


class ApprovalRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: UUID
    policy_code: str = Field(min_length=2, max_length=120)
    material_fingerprint: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class ApprovalRequestView(BaseModel):
    approval_request_id: UUID
    work_item_id: UUID
    requester_user_id: UUID
    policy_code: str
    policy_version: str
    status: str
    material_fingerprint: str
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern=r"^(APPROVED|REJECTED|REVISION_REQUESTED)$")
    reason: str = Field(min_length=3, max_length=2000)


class ExceptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: UUID | None = None
    category: str = Field(min_length=2, max_length=120)
    severity: str = Field(pattern=r"^(LOW|MEDIUM|HIGH|CRITICAL)$")
    due_at: datetime | None = None


class ExceptionView(BaseModel):
    exception_id: UUID
    work_item_id: UUID | None
    category: str
    severity: str
    status: str
    owner_user_id: UUID | None
    due_at: datetime | None
    created_at: datetime


class CapaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exception_id: UUID
    root_cause: str = Field(min_length=3, max_length=2000)
    corrective_action: str = Field(min_length=3, max_length=2000)
    preventive_action: str = Field(min_length=3, max_length=2000)
    due_at: datetime | None = None


class CapaView(BaseModel):
    capa_id: UUID
    exception_id: UUID
    status: str
    root_cause: str | None
    corrective_action: str | None
    preventive_action: str | None
    reviewer_user_id: UUID | None
    due_at: datetime | None
    closed_at: datetime | None
    created_at: datetime


class BudgetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,31}$")
    name: str = Field(min_length=3, max_length=160)
    currency: str = Field(default="IDR", pattern=r"^[A-Z]{3}$")
    allocated_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class BudgetView(BaseModel):
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


class PaymentRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    budget_id: UUID
    document_version_id: UUID
    payee_name: str = Field(min_length=2, max_length=200)
    purpose: str = Field(min_length=3, max_length=1000)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="IDR", pattern=r"^[A-Z]{3}$")
    requested_payment_date: date


class PaymentRequestView(BaseModel):
    payment_request_id: UUID
    work_item_id: UUID
    workflow_run_id: UUID
    approval_request_id: UUID | None
    project_id: UUID
    budget_id: UUID
    payee_name: str
    purpose: str
    amount: Decimal
    currency: str
    requested_payment_date: date
    status: str
    current_step: str
    budget_available: bool
    correlation_id: UUID
    created_at: datetime


class PaymentDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern=r"^(APPROVED|REJECTED|REVISION_REQUESTED)$")
    reason: str = Field(min_length=3, max_length=2000)


class PaymentRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_reference: str = Field(min_length=3, max_length=160)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="IDR", pattern=r"^[A-Z]{3}$")
    paid_at: datetime
    evidence_document_version_id: UUID


class ReconciliationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_reference: str = Field(min_length=3, max_length=160)
    transaction_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="IDR", pattern=r"^[A-Z]{3}$")


class FinanceWorkflowResult(BaseModel):
    payment_request_id: UUID
    workflow_run_id: UUID
    work_item_id: UUID
    approval_request_id: UUID | None
    current_step: str
    workflow_status: str
    payment_status: str
    work_item_status: WorkItemStatus
    reconciliation_status: str | None = None
    difference_amount: Decimal | None = None
    exception_id: UUID | None = None
    terminal: bool
    correlation_id: UUID


class SiteEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    document_version_id: UUID
    work_package_code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,39}$")
    claim_date: date
    claimed_progress: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    measured_progress: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    measurement_note: str = Field(min_length=3, max_length=2000)


class PropertyReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern=r"^(ACCEPTED|VARIANCE)$")
    verified_progress: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    notes: str = Field(min_length=3, max_length=2000)


class PropertyWorkflowResult(BaseModel):
    site_evidence_id: UUID
    workflow_run_id: UUID
    work_item_id: UUID
    current_step: str
    workflow_status: str
    evidence_status: str
    work_item_status: WorkItemStatus
    claimed_progress: Decimal
    measured_progress: Decimal
    variance: Decimal
    kpi_snapshot_id: UUID | None = None
    exception_id: UUID | None = None
    capa_id: UUID | None = None
    terminal: bool
    correlation_id: UUID


class LegalSubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    document_version_id: UUID
    document_type: str = Field(pattern=r"^(PERMIT|CONTRACT)$")
    reference_code: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=3, max_length=240)
    counterparty: str | None = Field(default=None, max_length=240)
    source_authority: str | None = Field(default=None, max_length=240)
    effective_date: date | None = None
    expiry_date: date | None = None

    @model_validator(mode="after")
    def validate_legal_metadata(self) -> "LegalSubmissionCreate":
        if self.document_type == "PERMIT" and not self.source_authority:
            raise ValueError("Izin wajib memiliki sumber atau instansi penerbit")
        if self.document_type == "CONTRACT" and not self.counterparty:
            raise ValueError("Kontrak wajib memiliki pihak lawan")
        if self.effective_date and self.expiry_date and self.expiry_date < self.effective_date:
            raise ValueError("Tanggal berakhir tidak boleh sebelum tanggal efektif")
        return self


class LegalReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern=r"^(APPROVED|REVISION_REQUESTED|REJECTED)$")
    legal_status: str = Field(pattern=r"^(VERIFIED|CONDITIONAL|NOT_APPROVED)$")
    official_source_verified: bool = False
    notes: str = Field(min_length=3, max_length=3000)


class LegalWorkflowResult(BaseModel):
    legal_case_id: UUID
    workflow_run_id: UUID
    work_item_id: UUID
    document_type: str
    current_step: str
    workflow_status: str
    case_status: str
    work_item_status: WorkItemStatus
    exception_id: UUID | None = None
    terminal: bool
    correlation_id: UUID


class RecruitmentRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    candidate_document_version_id: UUID
    position_title: str = Field(min_length=3, max_length=160)
    requesting_division_code: str = Field(
        pattern=r"^(FINANCE|SALES_MARKETING|PROPERTY|HR|LEGAL|IT)$"
    )
    employment_type: str = Field(pattern=r"^(PERMANENT|CONTRACT|INTERNSHIP)$")
    headcount: int = Field(ge=1, le=50)
    justification: str = Field(min_length=10, max_length=2000)
    criteria_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    candidate_alias: str = Field(min_length=2, max_length=80)
    required_criteria: list[str] = Field(min_length=1, max_length=30)
    met_criteria: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_recruitment_criteria(self) -> "RecruitmentRequestCreate":
        required = set(self.required_criteria)
        met = set(self.met_criteria)
        if len(required) != len(self.required_criteria) or len(met) != len(self.met_criteria):
            raise ValueError("Kriteria rekrutmen tidak boleh duplikat")
        for criterion in required | met:
            if not criterion or len(criterion) > 80 or not criterion.replace("_", "").isalnum():
                raise ValueError("Kode kriteria hanya boleh berisi huruf, angka, dan underscore")
        if not met.issubset(required):
            raise ValueError("Kriteria terpenuhi harus merupakan bagian dari kriteria wajib")
        return self


class RecruitmentDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern=r"^(SELECTED|REJECTED)$")
    notes: str = Field(min_length=3, max_length=3000)
    personnel_requirements: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_personnel_requirements(self) -> "RecruitmentDecisionCreate":
        requirements = set(self.personnel_requirements)
        if len(requirements) != len(self.personnel_requirements):
            raise ValueError("Persyaratan berkas personalia tidak boleh duplikat")
        if self.decision == "SELECTED" and not requirements:
            raise ValueError("Kandidat terpilih wajib memiliki checklist berkas personalia")
        if self.decision == "REJECTED" and requirements:
            raise ValueError("Kandidat ditolak tidak boleh dibuatkan checklist personalia")
        for requirement in requirements:
            if (
                not requirement
                or len(requirement) > 80
                or not requirement.replace("_", "").isalnum()
            ):
                raise ValueError("Kode persyaratan hanya boleh berisi huruf, angka, dan underscore")
        return self


class RecruitmentWorkflowResult(BaseModel):
    recruitment_request_id: UUID
    candidate_id: UUID
    workflow_run_id: UUID
    work_item_id: UUID
    current_step: str
    workflow_status: str
    recruitment_status: str
    screening_status: str
    missing_criteria: list[str]
    work_item_status: WorkItemStatus
    personnel_checklist_id: UUID | None = None
    terminal: bool
    correlation_id: UUID


class ExecutiveBriefCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    period_start: date
    period_end: date
    project_id: UUID | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "ExecutiveBriefCreate":
        if self.period_end < self.period_start:
            raise ValueError("Akhir periode tidak boleh sebelum awal periode")
        return self


class ExecutiveBriefReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern=r"^(PUBLISHED|REVISION_REQUESTED)$")
    notes: str = Field(min_length=3, max_length=3000)


class ExecutiveBriefResult(BaseModel):
    executive_brief_id: UUID
    executive_snapshot_id: UUID
    workflow_run_id: UUID
    current_step: str
    workflow_status: str
    brief_status: str
    title: str
    summary_counts: dict[str, int]
    narrative: str
    source_references: list[str]
    decision_item_count: int
    exception_id: UUID | None = None
    terminal: bool
    correlation_id: UUID
