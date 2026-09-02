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
    agent_kind: str
    parent_agent_id: str | None = None
    domain: str = "operations"
    parent_agent_version: str | None = None
    extends: str | None = None
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
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    status: str = "DRAFT"


class GenesisAnalyzeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    understanding: str
    strategy: GenesisStrategy
    strategy_justification: str
    parent_core_agent_id: str
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
