from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alos.security import Role


class UatRunStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_SIGNOFF = "READY_FOR_SIGNOFF"
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_RISK = "ACCEPTED_WITH_RISK"
    REJECTED = "REJECTED"


class UatScenarioStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    PASSED = "PASSED"
    PASSED_WITH_RISK = "PASSED_WITH_RISK"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class DefectSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignoffScope(StrEnum):
    SALES_MARKETING = "SALES_MARKETING"
    FINANCE = "FINANCE"
    PROPERTY = "PROPERTY"
    HR = "HR"
    LEGAL = "LEGAL"
    IT = "IT"
    AI_EXECUTIVE = "AI_EXECUTIVE"
    DIRECTOR = "DIRECTOR"


class SignoffDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_RISK = "ACCEPTED_WITH_RISK"
    REJECTED = "REJECTED"


class UatScenarioDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(pattern=r"^UAT-[0-9]{2}$")
    workspace: str = Field(min_length=2, max_length=80)
    division_code: str | None = Field(
        default=None, pattern=r"^[A-Z][A-Z0-9_]{1,39}$"
    )
    title: str = Field(min_length=3, max_length=160)
    objective: str = Field(min_length=10, max_length=1000)
    allowed_roles: frozenset[Role] = Field(min_length=1)


class UatCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    catalog_id: str = Field(pattern=r"^[A-Z][A-Z0-9-]{2,79}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    data_policy: str = Field(pattern=r"^SYNTHETIC_OR_SANITIZED$")
    required_signoff_scopes: frozenset[SignoffScope] = Field(min_length=1)
    scenarios: tuple[UatScenarioDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog(self) -> "UatCatalog":
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario_id UAT harus unik")
        if len(self.required_signoff_scopes) != len(SignoffScope):
            raise ValueError("Semua scope sign-off controlled pilot wajib tersedia")
        return self


class UatRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    title: str = Field(min_length=3, max_length=160)


class UatEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_version_id: UUID | None = None
    reference: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_reference(self) -> "UatEvidenceInput":
        if self.document_version_id is None and self.reference is None:
            raise ValueError("Evidence memerlukan dokumen atau referensi")
        return self


class UatScenarioRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UatScenarioStatus
    actual_result: str | None = Field(default=None, max_length=4000)
    defect_severity: DefectSeverity | None = None
    defect_summary: str | None = Field(default=None, max_length=2000)
    evidence: tuple[UatEvidenceInput, ...] = Field(default_factory=tuple, max_length=20)

    @model_validator(mode="after")
    def validate_result(self) -> "UatScenarioRecord":
        completed = self.status in {
            UatScenarioStatus.PASSED,
            UatScenarioStatus.PASSED_WITH_RISK,
        }
        if completed and (not self.actual_result or len(self.actual_result.strip()) < 8):
            raise ValueError("Skenario lulus wajib memiliki hasil aktual")
        if completed and not self.evidence:
            raise ValueError("Skenario lulus wajib memiliki minimal satu evidence")
        if self.status == UatScenarioStatus.PASSED and self.defect_severity is not None:
            raise ValueError("Status PASSED tidak boleh memiliki defect terbuka")
        if self.status == UatScenarioStatus.PASSED_WITH_RISK:
            if self.defect_severity not in {DefectSeverity.LOW, DefectSeverity.MEDIUM}:
                raise ValueError("Risk yang diterima hanya boleh LOW atau MEDIUM")
            if not self.defect_summary or len(self.defect_summary.strip()) < 8:
                raise ValueError("PASSED_WITH_RISK wajib menjelaskan risk")
        if self.status in {UatScenarioStatus.FAILED, UatScenarioStatus.BLOCKED}:
            if self.defect_severity is None:
                raise ValueError("FAILED atau BLOCKED wajib memiliki severity")
            if not self.defect_summary or len(self.defect_summary.strip()) < 8:
                raise ValueError("FAILED atau BLOCKED wajib menjelaskan temuan")
        return self


class UatSignoffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signoff_scope: SignoffScope
    decision: SignoffDecision
    risk_severity: DefectSeverity | None = None
    notes: str = Field(min_length=8, max_length=1000)

    @model_validator(mode="after")
    def validate_risk(self) -> "UatSignoffCreate":
        if self.decision == SignoffDecision.ACCEPTED_WITH_RISK:
            if self.risk_severity not in {DefectSeverity.LOW, DefectSeverity.MEDIUM}:
                raise ValueError("Sign-off dengan risk hanya boleh LOW atau MEDIUM")
        elif self.risk_severity is not None:
            raise ValueError("risk_severity hanya digunakan untuk ACCEPTED_WITH_RISK")
        return self


class UatEvidenceView(BaseModel):
    evidence_reference_id: UUID
    document_version_id: UUID | None
    reference: str | None
    created_at: datetime


class UatScenarioResultView(BaseModel):
    scenario_result_id: UUID
    scenario_id: str
    workspace: str
    division_code: str | None
    title: str
    objective: str
    allowed_roles: frozenset[Role]
    status: UatScenarioStatus
    tester_user_id: UUID | None
    actual_result: str | None
    defect_severity: DefectSeverity | None
    defect_summary: str | None
    tested_at: datetime | None
    evidence: tuple[UatEvidenceView, ...]
    version: int


class UatSignoffView(BaseModel):
    signoff_id: UUID
    signoff_scope: SignoffScope
    decision: SignoffDecision
    risk_severity: DefectSeverity | None
    signer_user_id: UUID | None
    signer_role: str
    notes: str
    signed_at: datetime


class UatRunView(BaseModel):
    uat_run_id: UUID
    organization_id: UUID
    project_id: UUID
    title: str
    cycle_number: int
    status: UatRunStatus
    data_policy: str
    created_by_user_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    scenarios: tuple[UatScenarioResultView, ...]
    signoffs: tuple[UatSignoffView, ...]
    required_signoff_scopes: frozenset[SignoffScope]
