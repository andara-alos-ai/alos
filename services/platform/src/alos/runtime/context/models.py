"""Typed, authority-neutral contracts for bounded runtime context assembly."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alos.genesis.governed_foundations import (
    ResearchDomain,
    Scope,
    SourceKind,
    SourceRequirement,
)
from alos.model_gateway import DataClassification
from alos.runtime.agentic.output import ExecutionContext


class ContextStatus(StrEnum):
    READY = "READY"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    BLOCKED = "BLOCKED"


class ContextErrorCode(StrEnum):
    EXECUTION_SCOPE_MISMATCH = "EXECUTION_SCOPE_MISMATCH"
    ACTOR_ROLE_NOT_AUTHORIZED = "ACTOR_ROLE_NOT_AUTHORIZED"
    CONTEXT_SCOPE_MISMATCH = "CONTEXT_SCOPE_MISMATCH"
    DATA_CLASSIFICATION_EXCEEDED = "DATA_CLASSIFICATION_EXCEEDED"
    UNAUTHORIZED_TOOL_CONTEXT = "UNAUTHORIZED_TOOL_CONTEXT"
    UNAUTHORIZED_CAPABILITY_CONTEXT = "UNAUTHORIZED_CAPABILITY_CONTEXT"
    UNTRUSTED_AUTHORITY_CONTEXT = "UNTRUSTED_AUTHORITY_CONTEXT"
    MANDATORY_CONTEXT_TOO_LARGE = "MANDATORY_CONTEXT_TOO_LARGE"
    EVIDENCE_CONTEXT_MISSING = "EVIDENCE_CONTEXT_MISSING"
    RESEARCH_DOMAIN_REQUIRED = "RESEARCH_DOMAIN_REQUIRED"
    RESEARCH_DOMAIN_NOT_AUTHORIZED = "RESEARCH_DOMAIN_NOT_AUTHORIZED"
    RESEARCH_DOMAIN_SCOPE_MISMATCH = "RESEARCH_DOMAIN_SCOPE_MISMATCH"
    RESEARCH_SOURCE_NOT_AUTHORIZED = "RESEARCH_SOURCE_NOT_AUTHORIZED"
    RESEARCH_CONTEXT_REQUIRED = "RESEARCH_CONTEXT_REQUIRED"
    RESEARCH_SOURCE_REQUIREMENTS_MISSING = "RESEARCH_SOURCE_REQUIREMENTS_MISSING"
    INTERNAL_EVIDENCE_INSUFFICIENT = "INTERNAL_EVIDENCE_INSUFFICIENT"
    EXTERNAL_RESEARCH_NOT_AUTHORIZED = "EXTERNAL_RESEARCH_NOT_AUTHORIZED"
    EXTERNAL_SOURCE_GOVERNANCE_REQUIRED = "EXTERNAL_SOURCE_GOVERNANCE_REQUIRED"
    EXTERNAL_RESEARCH_RISK_EXCEEDED = "EXTERNAL_RESEARCH_RISK_EXCEEDED"
    EXTERNAL_RESEARCH_COST_EXCEEDED = "EXTERNAL_RESEARCH_COST_EXCEEDED"


class ContextTrust(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    INTERNAL_APPROVED = "INTERNAL_APPROVED"
    EXTERNAL_UNTRUSTED = "EXTERNAL_UNTRUSTED"


class ContextPriority(StrEnum):
    MANDATORY = "MANDATORY"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class ContextItemKind(StrEnum):
    SYSTEM_RULE = "SYSTEM_RULE"
    CAPABILITY_CONTRACT = "CAPABILITY_CONTRACT"
    ACTOR_SCOPE = "ACTOR_SCOPE"
    EVIDENCE = "EVIDENCE"
    DATA = "DATA"
    MEMORY = "MEMORY"
    TOOL = "TOOL"
    CAPABILITY = "CAPABILITY"
    SOURCE = "SOURCE"


_AUTHORITY_KINDS = frozenset(
    {
        ContextItemKind.SYSTEM_RULE,
        ContextItemKind.CAPABILITY_CONTRACT,
        ContextItemKind.ACTOR_SCOPE,
        ContextItemKind.TOOL,
        ContextItemKind.CAPABILITY,
    }
)


class ContextItem(BaseModel):
    """One bounded context candidate; content is data and never grants authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
    kind: ContextItemKind
    scope: Scope
    classification: DataClassification
    trust: ContextTrust
    priority: ContextPriority = ContextPriority.NORMAL
    purpose: str = Field(min_length=3, max_length=2_000)
    provenance: tuple[str, ...] = ()
    estimated_tokens: int = Field(ge=1, le=10_000_000)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_trust_boundary(self) -> ContextItem:
        if self.trust == ContextTrust.EXTERNAL_UNTRUSTED and self.kind in _AUTHORITY_KINDS:
            raise ValueError("external context cannot represent authority-bearing context")
        if self.trust == ContextTrust.EXTERNAL_UNTRUSTED and not self.provenance:
            raise ValueError("external context requires provenance")
        if (
            self.trust == ContextTrust.EXTERNAL_UNTRUSTED
            and self.priority == ContextPriority.MANDATORY
        ):
            raise ValueError("external context cannot declare itself mandatory")
        if self.kind in {ContextItemKind.EVIDENCE, ContextItemKind.SOURCE} and not self.provenance:
            raise ValueError("evidence and source context require provenance")
        return self


class ContextBudget(BaseModel):
    """Human/config-controlled input envelope used by deterministic selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_input_tokens: int = Field(ge=1, le=10_000_000)
    reserved_input_tokens: int = Field(default=0, ge=0, le=9_999_999)
    max_items: int = Field(default=100, ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_available_budget(self) -> ContextBudget:
        if self.reserved_input_tokens >= self.max_input_tokens:
            raise ValueError("reserved input tokens must leave room for context")
        return self

    @property
    def available_context_tokens(self) -> int:
        return self.max_input_tokens - self.reserved_input_tokens


class ResearchEvidenceState(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    MISSING = "MISSING"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    UNRELIABLE = "UNRELIABLE"


class ResearchRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ResearchSourcePolicy(BaseModel):
    """Backend-supplied policy facts; this model never grants external access itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    external_research_allowed: bool = False
    approved_external_tool_available: bool = False
    external_egress_approved: bool = False
    maximum_external_risk: ResearchRiskLevel = ResearchRiskLevel.LOW
    max_external_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)


class ResearchDecisionContext(BaseModel):
    """Semantic evidence, risk, cost, and policy facts used for source selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    internal_evidence_state: ResearchEvidenceState
    evidence_gaps: tuple[str, ...] = ()
    risk_level: ResearchRiskLevel = ResearchRiskLevel.LOW
    estimated_external_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)
    source_policy: ResearchSourcePolicy = Field(default_factory=ResearchSourcePolicy)

    @model_validator(mode="after")
    def validate_evidence_state(self) -> ResearchDecisionContext:
        _require_unique("research evidence gaps", self.evidence_gaps)
        if self.internal_evidence_state == ResearchEvidenceState.SUFFICIENT:
            if self.evidence_gaps:
                raise ValueError("sufficient internal evidence cannot include evidence gaps")
        elif not self.evidence_gaps:
            raise ValueError("insufficient internal evidence requires explicit evidence gaps")
        return self


class ResearchDomainAccess(BaseModel):
    """Authoritative domain/scope/source envelope supplied to the AI context layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: ResearchDomain
    scope: Scope
    allowed_source_kinds: tuple[SourceKind, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_kinds(self) -> ResearchDomainAccess:
        if len(set(self.allowed_source_kinds)) != len(self.allowed_source_kinds):
            raise ValueError("allowed research source kinds must be unique")
        return self


class ContextBuildRequest(BaseModel):
    """Inputs already bounded by Backend authority before semantic assembly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str = Field(min_length=5, max_length=10_000)
    execution_context: ExecutionContext
    requested_scope: Scope
    contract_reference: str = Field(min_length=1, max_length=500)
    authorized_actor_roles: tuple[str, ...] = Field(min_length=1)
    authorized_capability_keys: tuple[str, ...] = ()
    authorized_tool_keys: tuple[str, ...] = ()
    candidate_items: tuple[ContextItem, ...] = ()
    evidence_references: tuple[str, ...] = ()
    source_requirements: tuple[SourceRequirement, ...] = ()
    requires_research: bool = False
    research_domain: ResearchDomain | None = None
    research_context: ResearchDecisionContext | None = None
    research_domain_access: tuple[ResearchDomainAccess, ...] = ()
    budget: ContextBudget

    @model_validator(mode="after")
    def validate_request_identity(self) -> ContextBuildRequest:
        _require_unique("authorized actor roles", self.authorized_actor_roles)
        _require_unique("authorized capability keys", self.authorized_capability_keys)
        _require_unique("authorized tool keys", self.authorized_tool_keys)
        _require_unique("candidate context keys", tuple(item.key for item in self.candidate_items))
        _require_unique("evidence references", self.evidence_references)
        _require_unique(
            "source requirements",
            tuple(item.model_dump_json() for item in self.source_requirements),
        )
        domain_keys = tuple(item.domain.value for item in self.research_domain_access)
        _require_unique("research domain access entries", domain_keys)
        if any(not role.strip() for role in self.authorized_actor_roles):
            raise ValueError("authorized actor roles cannot contain blank values")
        if self.research_domain is not None and not self.requires_research:
            raise ValueError("research_domain requires requires_research=true")
        if self.research_context is not None and not self.requires_research:
            raise ValueError("research_context requires requires_research=true")
        return self


class ContextBundle(BaseModel):
    """Validated context payload ready for a provider-neutral agentic request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str = Field(min_length=5, max_length=10_000)
    execution_context: ExecutionContext
    scope: Scope
    contract_reference: str = Field(min_length=1, max_length=500)
    allowed_actor_roles: tuple[str, ...] = Field(min_length=1)
    selected_items: tuple[ContextItem, ...]
    allowed_capability_keys: tuple[str, ...] = ()
    allowed_tool_keys: tuple[str, ...] = ()
    source_requirements: tuple[SourceRequirement, ...] = ()
    evidence_references: tuple[str, ...] = ()
    research_domain: ResearchDomain | None = None
    token_limit: int = Field(ge=1, le=10_000_000)
    used_tokens: int = Field(ge=0, le=10_000_000)
    omitted_item_keys: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    external_content_untrusted: Literal[True] = True
    context_grants_authority: Literal[False] = False
    backend_authority_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_bundle_envelope(self) -> ContextBundle:
        selected_keys = tuple(item.key for item in self.selected_items)
        _require_unique("selected context keys", selected_keys)
        _require_unique("omitted context keys", self.omitted_item_keys)
        _require_unique("allowed actor roles", self.allowed_actor_roles)
        if set(selected_keys).intersection(self.omitted_item_keys):
            raise ValueError("selected and omitted context keys must be disjoint")
        if self.execution_context.actor_role not in self.allowed_actor_roles:
            raise ValueError("execution actor role is absent from the allowed role envelope")
        if self.used_tokens > self.token_limit:
            raise ValueError("context bundle exceeds its token limit")
        if sum(item.estimated_tokens for item in self.selected_items) != self.used_tokens:
            raise ValueError("used_tokens must equal selected item token estimates")
        return self


class ResearchSourceDecisionKind(StrEnum):
    INTERNAL_SUFFICIENT = "INTERNAL_SUFFICIENT"
    EXTERNAL_RESEARCH_REQUIRED = "EXTERNAL_RESEARCH_REQUIRED"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    BLOCKED = "BLOCKED"


class ResearchSourceDecision(BaseModel):
    """Semantic source decision; it cannot grant access, permission, or authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: ResearchSourceDecisionKind
    rationale: str = Field(min_length=10, max_length=2_000)
    source_requirements: tuple[SourceRequirement, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    error_code: ContextErrorCode | None = None
    external_content_untrusted: Literal[True] = True
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_decision_shape(self) -> ResearchSourceDecision:
        terminal_error = self.decision in {
            ResearchSourceDecisionKind.NEEDS_INFORMATION,
            ResearchSourceDecisionKind.BLOCKED,
        }
        if terminal_error and self.error_code is None:
            raise ValueError("non-ready source decision requires an error code")
        if not terminal_error and self.error_code is not None:
            raise ValueError("ready source decision cannot include an error code")
        return self


class ContextBuildResult(BaseModel):
    """Fail-closed result shape returned by the Context Builder."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ContextStatus
    bundle: ContextBundle | None = None
    source_decision: ResearchSourceDecision | None = None
    error_code: ContextErrorCode | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> ContextBuildResult:
        if self.status == ContextStatus.READY:
            if self.bundle is None:
                raise ValueError("READY context result requires a bundle")
            if self.error_code is not None or self.reason is not None:
                raise ValueError("READY context result cannot include an error")
            if (
                self.source_decision is not None
                and self.source_decision.decision
                in {
                    ResearchSourceDecisionKind.NEEDS_INFORMATION,
                    ResearchSourceDecisionKind.BLOCKED,
                }
            ):
                raise ValueError("READY context result requires a ready source decision")
        else:
            if self.bundle is not None:
                raise ValueError("non-ready context result cannot include a bundle")
            if self.error_code is None or self.reason is None:
                raise ValueError("non-ready context result requires an error and reason")
        return self


def _require_unique(label: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")
