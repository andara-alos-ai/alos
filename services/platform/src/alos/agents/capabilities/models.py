import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alos.agents.contract import CapabilityExecutionMode


class CapabilityStatus(StrEnum):
    DRAFT = "DRAFT"
    STAGED = "STAGED"
    RELEASED = "RELEASED"
    RETIRED = "RETIRED"


class CapabilityEvidencePolicy(StrEnum):
    NONE = "NONE"
    WHEN_AVAILABLE = "WHEN_AVAILABLE"
    REQUIRED = "REQUIRED"


class CapabilityReviewPolicy(StrEnum):
    NEVER = "NEVER"
    ON_WARNING = "ON_WARNING"
    ALWAYS = "ALWAYS"


class CapabilityContract(BaseModel):
    """Versioned contract shared by Core, Sub-Agent, and Sub-Sub-Agent runtimes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,127}$")
    name: str = Field(min_length=3, max_length=120)
    purpose: str = Field(min_length=10, max_length=500)
    execution_mode: CapabilityExecutionMode
    handler_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    evidence_policy: CapabilityEvidencePolicy
    review_policy: CapabilityReviewPolicy
    timeout_seconds: int = Field(ge=1, le=300)
    max_attempts: int = Field(ge=1, le=5)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: CapabilityStatus

    @field_validator("input_schema", "output_schema")
    @classmethod
    def require_object_schema(cls, value: dict[str, object]) -> dict[str, object]:
        if value.get("type") != "object":
            raise ValueError("Capability schema wajib JSON Schema bertipe object")
        if value.get("additionalProperties") is not False:
            raise ValueError("Capability schema wajib menolak additionalProperties")
        properties = value.get("properties")
        if not isinstance(properties, dict) or not properties:
            raise ValueError("Capability schema wajib mendefinisikan properties")
        return value

    def canonical_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"status"})

    @property
    def contract_digest(self) -> str:
        payload = json.dumps(
            self.canonical_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
