from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReadinessCheckStatus(StrEnum):
    PASS = "PASS"  # noqa: S105 -- readiness status, not a credential
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class ReadinessOverallStatus(StrEnum):
    READY = "READY"
    ATTENTION = "ATTENTION"
    BLOCKED = "BLOCKED"


class PilotRoleRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(pattern=r"^PILOT-[A-Z0-9-]{3,60}$")
    title: str = Field(min_length=3, max_length=160)
    role_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,39}$")
    division_code: str | None = Field(
        default=None, pattern=r"^[A-Z][A-Z0-9_]{1,39}$"
    )
    minimum_active_users: int = Field(ge=1, le=20)
    project_assignment_required: bool = False
    division_head_allowed: bool = False


class PilotReadinessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    profile_id: str = Field(pattern=r"^[A-Z][A-Z0-9-]{2,79}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: str = Field(pattern=r"^(DRAFT|PILOT|ACTIVE|RETIRED)$")
    data_policy: str = Field(pattern=r"^SYNTHETIC_OR_SANITIZED$")
    required_divisions: frozenset[str] = Field(min_length=1)
    role_requirements: tuple[PilotRoleRequirement, ...] = Field(min_length=1)
    minimum_registered_agents: int = Field(ge=1, le=100)
    expected_workflows: int = Field(ge=1, le=100)
    minimum_safe_documents: int = Field(ge=1, le=1000)
    worker_max_age_minutes: int = Field(ge=1, le=60)
    production_effect: bool = False

    @model_validator(mode="after")
    def validate_profile(self) -> "PilotReadinessProfile":
        if self.production_effect:
            raise ValueError("Profil controlled pilot tidak boleh memiliki production effect")
        check_ids = [item.check_id for item in self.role_requirements]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("check_id role requirement harus unik")
        division_requirements = {
            item.division_code
            for item in self.role_requirements
            if item.division_code is not None
        }
        if not division_requirements.issubset(self.required_divisions):
            raise ValueError("Role requirement merujuk divisi di luar profil")
        return self


class PilotReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(pattern=r"^PILOT-[A-Z0-9-]{3,60}$")
    category: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,39}$")
    title: str = Field(min_length=3, max_length=160)
    status: ReadinessCheckStatus
    required: bool
    detail: str = Field(min_length=3, max_length=500)
    remediation: str | None = Field(default=None, min_length=3, max_length=500)
    actual_count: int | None = Field(default=None, ge=0)
    target_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_blocking_semantics(self) -> "PilotReadinessCheck":
        if self.status == ReadinessCheckStatus.BLOCKED and not self.required:
            raise ValueError("Status BLOCKED hanya untuk pemeriksaan wajib")
        if self.status != ReadinessCheckStatus.PASS and self.remediation is None:
            raise ValueError("Pemeriksaan yang belum lulus wajib memiliki remediation")
        if (self.actual_count is None) != (self.target_count is None):
            raise ValueError("Actual dan target count harus diberikan bersama")
        return self


class PilotReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    project_id: UUID
    environment: str
    evaluated_at: datetime
    overall_status: ReadinessOverallStatus
    passed_checks: int = Field(ge=0)
    warning_checks: int = Field(ge=0)
    blocked_checks: int = Field(ge=0)
    checks: tuple[PilotReadinessCheck, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_summary(self) -> "PilotReadinessReport":
        counts = {
            ReadinessCheckStatus.PASS: self.passed_checks,
            ReadinessCheckStatus.WARNING: self.warning_checks,
            ReadinessCheckStatus.BLOCKED: self.blocked_checks,
        }
        for status, expected in counts.items():
            actual = sum(check.status == status for check in self.checks)
            if actual != expected:
                raise ValueError(f"Ringkasan readiness tidak cocok untuk {status.value}")
        expected_overall = (
            ReadinessOverallStatus.BLOCKED
            if self.blocked_checks
            else ReadinessOverallStatus.ATTENTION
            if self.warning_checks
            else ReadinessOverallStatus.READY
        )
        if self.overall_status != expected_overall:
            raise ValueError("Overall status readiness tidak konsisten")
        return self
