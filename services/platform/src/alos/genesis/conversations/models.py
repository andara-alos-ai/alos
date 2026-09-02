from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alos.genesis.analysis.models import GenesisAnalyzeResult
from alos.genesis.models import GenesisFieldDiff


class GenesisConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    RELEASED = "RELEASED"


class GenesisSenderType(StrEnum):
    USER = "USER"
    GENESIS_ASSISTANT = "GENESIS_ASSISTANT"
    SYSTEM = "SYSTEM"


class GenesisConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=200)
    project_id: UUID | None = None
    initial_prompt: str | None = Field(default=None, max_length=4000)
    source_references: tuple[str, ...] = Field(default=())
    division_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,31}$")

    @field_validator("source_references")
    @classmethod
    def validate_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError("source_references tidak boleh kosong atau memiliki spasi di tepi")
        if len(values) != len(set(values)):
            raise ValueError("source_references tidak boleh duplikat")
        return values


class GenesisMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_text: str = Field(min_length=1, max_length=4000)
    source_references: tuple[str, ...] = Field(default=())
    division_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,31}$")

    @field_validator("source_references")
    @classmethod
    def validate_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError("source_references tidak boleh kosong atau memiliki spasi di tepi")
        if len(values) != len(set(values)):
            raise ValueError("source_references tidak boleh duplikat")
        return values


class GenesisMessageView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: UUID
    conversation_id: UUID
    sender_type: GenesisSenderType
    sender_user_id: UUID | None
    message_text: str
    analysis_result: GenesisAnalyzeResult | None = None
    created_at: datetime
    source_references: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenesisArtifactVersionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_version_id: UUID
    conversation_id: UUID
    version_number: int
    agent_id: str
    spec_data: dict[str, Any]
    created_by_user_id: UUID
    change_summary: str
    created_at: datetime
    diff: tuple[GenesisFieldDiff, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    pipeline_request_id: UUID | None = None


class GenesisConversationView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    organization_id: UUID
    project_id: UUID | None
    created_by_user_id: UUID
    title: str
    status: GenesisConversationStatus
    context_data: dict[str, Any] = Field(default_factory=dict)
    messages: tuple[GenesisMessageView, ...] = ()
    artifact_versions: tuple[GenesisArtifactVersionView, ...] = ()
    created_at: datetime
    updated_at: datetime


class GenesisConversationListItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    organization_id: UUID
    project_id: UUID | None
    created_by_user_id: UUID
    title: str
    status: GenesisConversationStatus
    message_count: int
    artifact_version_count: int
    created_at: datetime
    updated_at: datetime
