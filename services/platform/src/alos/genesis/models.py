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
