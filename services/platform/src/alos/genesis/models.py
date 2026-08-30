from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from alos.agents.contract import AgentDefinition, AgentReference


class GenesisStrategy(StrEnum):
    REUSE = "REUSE"
    EXTEND = "EXTEND"
    CREATE = "CREATE"


class GenesisProposalStatus(StrEnum):
    INVALID = "INVALID"
    AWAITING_HUMAN_REVIEW = "AWAITING_HUMAN_REVIEW"


class GenesisLifecycleStatus(StrEnum):
    INVALID = "INVALID"
    AWAITING_HUMAN_REVIEW = "AWAITING_HUMAN_REVIEW"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    STAGED = "STAGED"
    RELEASED = "RELEASED"


class GenesisReviewGate(StrEnum):
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"


class GenesisReviewDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class GenesisValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    passed: bool
    message: str = Field(min_length=3, max_length=500)


class GenesisFieldDiff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    before: object | None = None
    after: object | None = None


class GenesisChangeRequest(BaseModel):
    """Validated input boundary for a future Genesis analyzer/generator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: GenesisStrategy
    requested_by: str = Field(min_length=3, max_length=120)
    justification: str = Field(min_length=12, max_length=1000)
    source_references: tuple[str, ...] = Field(min_length=1)
    target: AgentReference | None = None
    base: AgentReference | None = None
    candidate: AgentDefinition | None = None

    @field_validator("source_references")
    @classmethod
    def validate_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError("source_references tidak boleh kosong atau memiliki spasi di tepi")
        if len(values) != len(set(values)):
            raise ValueError("source_references tidak boleh duplikat")
        return values

    @model_validator(mode="after")
    def validate_strategy_payload(self) -> "GenesisChangeRequest":
        if self.strategy == GenesisStrategy.REUSE:
            if self.target is None or self.base is not None or self.candidate is not None:
                raise ValueError("REUSE hanya memerlukan target")
        elif self.strategy == GenesisStrategy.EXTEND:
            if self.base is None or self.candidate is None or self.target is not None:
                raise ValueError("EXTEND memerlukan base dan candidate")
        elif self.candidate is None or self.target is not None or self.base is not None:
            raise ValueError("CREATE hanya memerlukan candidate")
        return self


class GenesisProposal(BaseModel):
    """Read-only proposal artifact that must pass human review before any staging process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: UUID
    strategy: GenesisStrategy
    status: GenesisProposalStatus
    requested_by: str
    source_references: tuple[str, ...]
    resolved_contract: AgentDefinition | None
    resolved_reference: AgentReference | None
    validations: tuple[GenesisValidation, ...]
    diff: tuple[GenesisFieldDiff, ...]
    production_effect: bool = False
    next_allowed_action: str = "HUMAN_REVIEW"
    created_at: datetime


class GenesisSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: GenesisStrategy
    justification: str = Field(min_length=12, max_length=1000)
    source_references: tuple[str, ...] = Field(min_length=1)
    target: AgentReference | None = None
    base: AgentReference | None = None
    candidate: AgentDefinition | None = None

    @model_validator(mode="after")
    def validate_strategy_payload(self) -> "GenesisSubmitRequest":
        GenesisChangeRequest(
            strategy=self.strategy,
            requested_by="validation-only",
            justification=self.justification,
            source_references=self.source_references,
            target=self.target,
            base=self.base,
            candidate=self.candidate,
        )
        return self

    def to_change_request(self, requested_by: UUID) -> GenesisChangeRequest:
        return GenesisChangeRequest(
            **self.model_dump(),
            requested_by=str(requested_by),
        )


class GenesisReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gate: GenesisReviewGate
    decision: GenesisReviewDecision
    notes: str = Field(min_length=8, max_length=2000)


class GenesisReviewView(BaseModel):
    review_id: UUID
    gate: GenesisReviewGate
    decision: GenesisReviewDecision
    reviewer_user_id: UUID
    notes: str
    reviewed_at: datetime


class GenesisTestResult(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    passed: bool
    message: str = Field(min_length=3, max_length=500)


class GenesisReleaseView(BaseModel):
    release_id: UUID
    status: str
    contract_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    staged_by_user_id: UUID
    released_by_user_id: UUID | None
    staged_at: datetime
    released_at: datetime | None
    production_effect: bool = False


class GenesisPipelineView(BaseModel):
    request_id: UUID
    organization_id: UUID
    strategy: GenesisStrategy
    requested_by_user_id: UUID
    justification: str
    source_references: tuple[str, ...]
    status: GenesisLifecycleStatus
    proposal: GenesisProposal
    tests: tuple[GenesisTestResult, ...]
    reviews: tuple[GenesisReviewView, ...]
    release: GenesisReleaseView | None = None
    production_effect: bool = False
    next_allowed_action: str
    created_at: datetime
    updated_at: datetime
