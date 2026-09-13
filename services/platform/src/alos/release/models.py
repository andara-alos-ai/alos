"""Public release-governance request/response models and type aliases."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from alos.identity import DivisionCode, HumanRole

TestCategory = Literal["POSITIVE", "NEGATIVE", "REGRESSION", "SECURITY", "RECOVERY"]
ReviewGate = Literal["BUSINESS", "TECHNICAL"]
ReviewDecision = Literal["APPROVED", "REJECTED", "RETURNED"]
ReleaseState = Literal[
    "DRAFT",
    "TESTED",
    "IN_REVIEW",
    "RETURNED",
    "REJECTED",
    "APPROVED",
    "RELEASED",
    "ACTIVE",
    "SUSPENDED",
    "ROLLED_BACK",
]
LocalReleaseDuty = Literal[
    "MAKER", "CHECKER", "BUSINESS_REVIEWER", "TECHNICAL_REVIEWER", "APPROVER"
]


class TestCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    category: TestCategory
    input_fixture: dict[str, Any]
    expected_assertions: dict[str, Any]


class ReleaseRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    tenant_id: UUID | None = None
    requirement: str = Field(min_length=20, max_length=10_000)


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=10_000)


class TestCaseRecord(TestCaseRequest):
    test_case_id: UUID
    agent_key: str
    agent_version_id: UUID


class ReleaseRequestRecord(BaseModel):
    change_request_id: UUID
    agent_key: str
    agent_version_id: UUID
    semantic_version: str
    state: ReleaseState
    requested_by_user_id: UUID
    maker_user_id: UUID
    checker_user_id: UUID | None
    approver_user_id: UUID | None
    kill_switch_active: bool = False
    failed_test_count: int = 0


class TestRunEvidence(BaseModel):
    test_run_id: UUID
    test_case_id: UUID
    test_key: str
    category: TestCategory
    status: Literal["PASSED", "FAILED", "BLOCKED", "ERROR"]
    agent_run_id: UUID | None
    correlation_id: UUID
    completed_at: datetime | None
    actual_status: str | None = None
    error_code: str | None = None
    block_reason: str | None = None
    evidence_id: UUID | None = None
    evaluator: str | None = None
    score: float | None = None


class ReviewRecord(BaseModel):
    review_gate: ReviewGate
    decision: ReviewDecision
    notes: str
    reviewer_user_id: UUID
    reviewer_name: str
    division_code: str | None
    created_at: datetime


class LifecycleEventRecord(BaseModel):
    event_sequence: int
    from_state: ReleaseState | None
    to_state: ReleaseState
    reason: str
    correlation_id: UUID
    created_at: datetime


class ReleaseRequestDetail(ReleaseRequestRecord):
    requirement: str
    test_cases: list[TestCaseRecord]
    test_runs: list[TestRunEvidence]
    reviews: list[ReviewRecord]
    lifecycle_events: list[LifecycleEventRecord]
    kill_switch_active: bool
    rollback_targets: list[str]


class TestExecutionResult(BaseModel):
    test_run_id: UUID
    test_key: str
    status: Literal["PASSED", "FAILED", "BLOCKED", "ERROR"]
    agent_run_id: UUID | None
    evidence_id: UUID
    evaluator: str
    score: float | None = None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: ReviewGate
    decision: ReviewDecision
    notes: str = Field(min_length=1, max_length=10_000)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_semantic_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    reason: str = Field(min_length=1, max_length=10_000)


class LocalReleaseParticipant(BaseModel):
    duty: LocalReleaseDuty
    user_id: UUID
    email: str
    role: HumanRole


class LocalReleaseTeam(BaseModel):
    organization_id: UUID
    workspace_id: UUID
    division_code: DivisionCode
    participants: list[LocalReleaseParticipant]
