import hashlib
import json
from enum import StrEnum

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SEMANTIC_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
AGENT_ID_PATTERN = r"^[A-Z][A-Z0-9_]{1,63}$"


class AgentStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    TESTED = "TESTED"
    REVIEWED = "REVIEWED"
    STAGED = "STAGED"
    RELEASED = "RELEASED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ROLLED_BACK = "ROLLED_BACK"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class AgentKind(StrEnum):
    CORE = "CORE"
    SUB_AGENT = "SUB_AGENT"
    SUB_SUB_AGENT = "SUB_SUB_AGENT"
    LOGICAL = "LOGICAL"


class CapabilityExecutionMode(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    AI_ASSISTED = "AI_ASSISTED"


class AgentReference(BaseModel):
    """Exact reference to a versioned Agent Contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    version: str = Field(pattern=SEMANTIC_VERSION_PATTERN)


class AgentDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    contract_version: str = Field(pattern=SEMANTIC_VERSION_PATTERN)
    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    name: str = Field(min_length=3, max_length=120)
    agent_kind: AgentKind
    parent_agent_id: str | None = Field(default=None, pattern=AGENT_ID_PATTERN)
    parent_agent_version: str | None = Field(default=None, pattern=SEMANTIC_VERSION_PATTERN)
    extends: AgentReference | None = None
    domain: str = Field(min_length=2, max_length=64)
    division_scope: tuple[str, ...] = ()
    purpose: str = Field(min_length=20)
    human_owner: str = Field(min_length=3)
    triggers: tuple[str, ...] = Field(min_length=1)
    inputs: tuple[str, ...] = Field(min_length=1)
    source_of_truth: tuple[str, ...] = Field(min_length=1)
    capabilities: tuple[str, ...] = Field(min_length=1)
    outputs: tuple[str, ...] = Field(min_length=1)
    tools_allowed: tuple[str, ...]
    approval_boundary: tuple[str, ...] = Field(min_length=1)
    evidence_requirement: tuple[str, ...] = Field(min_length=1)
    forbidden_actions: tuple[str, ...] = Field(min_length=1)
    metrics: tuple[str, ...] = Field(
        validation_alias=AliasChoices("metrics", "KPI/metrics"),
        serialization_alias="metrics",
        min_length=1,
    )
    escalation: tuple[str, ...] = Field(min_length=1)
    prompt_ref: str | None = Field(default=None, min_length=3, max_length=160)
    model_policy_ref: str | None = Field(default=None, min_length=3, max_length=160)
    permission_policy_ref: str | None = Field(default=None, min_length=3, max_length=160)
    risk_level: str | None = Field(default=None, pattern=r"^(LOW|MEDIUM|HIGH|CRITICAL)$")
    input_schema: dict[str, object] | None = None
    output_schema: dict[str, object] | None = None
    rollback_target: AgentReference | None = None
    version: str = Field(pattern=SEMANTIC_VERSION_PATTERN)
    status: AgentStatus

    @field_validator(
        "triggers",
        "inputs",
        "source_of_truth",
        "capabilities",
        "outputs",
        "tools_allowed",
        "approval_boundary",
        "evidence_requirement",
        "forbidden_actions",
        "metrics",
        "escalation",
    )
    @classmethod
    def reject_blank_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError("daftar tidak boleh memuat nilai kosong atau spasi di tepi")
        if len(values) != len(set(values)):
            raise ValueError("daftar tidak boleh memuat nilai duplikat")
        return values

    @model_validator(mode="after")
    def validate_hierarchy_metadata(self) -> "AgentDefinition":
        has_parent_id = self.parent_agent_id is not None
        has_parent_version = self.parent_agent_version is not None
        if has_parent_id != has_parent_version:
            raise ValueError("parent_agent_id dan parent_agent_version wajib diisi bersama")
        if self.agent_kind == AgentKind.CORE and has_parent_id:
            raise ValueError("Core Agent tidak boleh memiliki parent")
        if self.agent_kind in {AgentKind.SUB_AGENT, AgentKind.SUB_SUB_AGENT} and not has_parent_id:
            raise ValueError("Sub-Agent dan Sub-Sub-Agent wajib memiliki parent")
        if self.parent_agent_id == self.agent_id:
            raise ValueError("agent tidak boleh menjadi parent dirinya sendiri")
        if self.extends == AgentReference(agent_id=self.agent_id, version=self.version):
            raise ValueError("agent tidak boleh melakukan extends terhadap versinya sendiri")
        if self.agent_kind == AgentKind.LOGICAL:
            required = {
                "division_scope": self.division_scope,
                "prompt_ref": self.prompt_ref,
                "model_policy_ref": self.model_policy_ref,
                "permission_policy_ref": self.permission_policy_ref,
                "risk_level": self.risk_level,
                "input_schema": self.input_schema,
                "output_schema": self.output_schema,
            }
            missing = sorted(name for name, value in required.items() if not value)
            if missing:
                raise ValueError(
                    "Logical Agent wajib memiliki kontrak MVP1 lengkap: " + ", ".join(missing)
                )
        return self

    def canonical_payload(self) -> dict[str, object]:
        """Return immutable contract content; lifecycle status is release metadata."""

        return self.model_dump(
            mode="json",
            by_alias=False,
            exclude_none=False,
            exclude={"status"},
        )

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def contract_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
