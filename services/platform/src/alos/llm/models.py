from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMProvider(StrEnum):
    DISABLED = "disabled"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class DataClassification(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3


class LLMResultStatus(StrEnum):
    COMPLETED = "COMPLETED"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_id: str = Field(pattern=r"^[a-z][a-z0-9.-]{2,127}$")
    prompt_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    input_data: dict[str, Any]
    classification: DataClassification = DataClassification.INTERNAL
    safety_identifier: str = Field(min_length=3, max_length=200)
    max_output_tokens: int = Field(default=800, ge=32, le=8192)


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class LLMResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: LLMResultStatus
    output: dict[str, Any] = Field(default_factory=dict)
    provider: LLMProvider
    model: str | None = None
    prompt_id: str
    prompt_version: str
    prompt_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_request_id: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    latency_ms: int = Field(default=0, ge=0)
    redacted_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @field_validator("redacted_fields", "warnings")
    @classmethod
    def unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("Metadata LLM tidak boleh duplikat")
        return values
