from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolKind(StrEnum):
    INTERNAL = "INTERNAL"
    DETERMINISTIC = "DETERMINISTIC"
    AI_PROVIDER = "AI_PROVIDER"


class ToolEffect(StrEnum):
    READ_ONLY = "READ_ONLY"
    STATE_CHANGING = "STATE_CHANGING"
    COMPUTE = "COMPUTE"
    AI_ASSISTED = "AI_ASSISTED"


class ToolCredentialMode(StrEnum):
    NONE = "NONE"
    EXECUTION_CONTEXT = "EXECUTION_CONTEXT"
    PLATFORM_MANAGED = "PLATFORM_MANAGED"


class ToolStatus(StrEnum):
    DRAFT = "DRAFT"
    STAGED = "STAGED"
    RELEASED = "RELEASED"
    DEPRECATED = "DEPRECATED"


class ToolReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class ToolContract(BaseModel):
    """Technical contract for one allow-listed runtime operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    tool_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    name: str = Field(min_length=3, max_length=120)
    purpose: str = Field(min_length=12, max_length=300)
    kind: ToolKind
    effect: ToolEffect
    credential_mode: ToolCredentialMode
    allowed_in_deterministic_steps: bool
    timeout_seconds: int = Field(ge=1, le=120)
    max_attempts: int = Field(ge=1, le=5)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: ToolStatus

    @model_validator(mode="after")
    def validate_execution_semantics(self) -> "ToolContract":
        if self.kind == ToolKind.AI_PROVIDER:
            if self.effect != ToolEffect.AI_ASSISTED:
                raise ValueError("AI provider wajib memiliki effect AI_ASSISTED")
            if self.allowed_in_deterministic_steps:
                raise ValueError("AI provider tidak boleh digunakan pada langkah deterministik")
        if self.kind == ToolKind.DETERMINISTIC and self.effect != ToolEffect.COMPUTE:
            raise ValueError("Tool deterministik wajib memiliki effect COMPUTE")
        return self
