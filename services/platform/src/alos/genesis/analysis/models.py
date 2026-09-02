from pydantic import BaseModel, ConfigDict, Field, field_validator

from alos.genesis.models import GenesisStrategy, GenesisValidation


class GenesisAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=5, max_length=4000)
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


class GenesisAnalyzeWorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    name: str
    actor: str
    description: str


class GenesisAnalyzeWorkflowProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_name: str
    steps: tuple[GenesisAnalyzeWorkflowStep, ...] = ()


class GenesisAnalyzeLLMMetadata(BaseModel):
    """Safe provenance metadata retained with every Genesis analysis result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str | None = None
    prompt_id: str
    prompt_version: str
    prompt_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    redacted_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _legacy_llm_metadata() -> GenesisAnalyzeLLMMetadata:
    """Allow read-only loading of analysis artifacts created before provenance fields."""

    return GenesisAnalyzeLLMMetadata(
        provider="unknown",
        prompt_id="genesis.analyze",
        prompt_version="1.0.0",
        prompt_digest="0" * 64,
        warnings=("Metadata LLM tidak tersedia pada artifact legacy.",),
    )


class GenesisAnalyzeContractDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    name: str
    purpose: str
    agent_kind: str = "LOGICAL"
    domain: str = "shared-enterprise"
    division_scope: tuple[str, ...] = ()
    contract_version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    human_owner: str = "Pemilik proses terkait"
    triggers: tuple[str, ...] = ("Permintaan pengguna berwenang",)
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    source_of_truth: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    tools_allowed: tuple[str, ...] = ()
    approval_boundary: tuple[str, ...] = ()
    evidence_requirement: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    kpi_metrics: tuple[str, ...] = ()
    escalation: tuple[str, ...] = ("Eskalasi ke pemilik proses manusia",)
    prompt_ref: str = "genesis.validation@0.1.0"
    model_policy_ref: str = "openai-primary-claude-fallback@0.1.0"
    permission_policy_ref: str = "read-only-evidence@0.1.0"
    risk_level: str = "LOW"
    input_schema: dict[str, object] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": False}
    )
    output_schema: dict[str, object] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": False}
    )
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    status: str = "DRAFT"


class GenesisAnalyzeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    understanding: str
    strategy: GenesisStrategy
    strategy_justification: str
    runtime_scope: str = "SHARED_AGENT_RUNTIME"
    business_owner: str
    domain: str
    agent_contract_draft: GenesisAnalyzeContractDraft
    workflow_proposal: GenesisAnalyzeWorkflowProposal
    risks_and_blockers: tuple[str, ...] = ()
    unanswered_questions: tuple[str, ...] = ()
    governance_notes: str = "Proposal berstatus DRAFT pada design-time. production_effect=false."
    validations: tuple[GenesisValidation, ...] = ()
    production_effect: bool = False
    source_references: tuple[str, ...] = ()
    llm_result_status: str = "COMPLETED"
    llm_metadata: GenesisAnalyzeLLMMetadata = Field(default_factory=_legacy_llm_metadata)
