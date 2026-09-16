"""Typed domain models shared across the GENESIS factory pipeline."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alos.genesis.governed_foundations import (
    ResearchDomain,
    SourceRequirement,
)
from alos.genesis.governed_foundations import SourceKind as SourceKind


class ImplementationType(StrEnum):
    AGENT = "AGENT"
    SKILL = "SKILL"
    WORKFLOW = "WORKFLOW"
    RULE = "RULE"
    VALIDATOR = "VALIDATOR"
    REPORT = "REPORT"
    HUMAN_TASK = "HUMAN_TASK"
    SCHEDULE = "SCHEDULE"
    EVENT_HANDLER = "EVENT_HANDLER"
    CONNECTOR_REQUIREMENT = "CONNECTOR_REQUIREMENT"
    TOOL_REQUIREMENT = "TOOL_REQUIREMENT"
    COMPOSITE = "COMPOSITE"


class TriggerKind(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    EVENT = "EVENT"
    CONDITIONAL = "CONDITIONAL"


class RequirementUnderstanding(BaseModel):
    """Semantically extracted facts; no implementation choice is made here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str = Field(min_length=5, max_length=10_000)
    trigger_kind: TriggerKind
    required_capabilities: tuple[str, ...] = ()
    required_data: tuple[str, ...] = ()
    desired_outputs: tuple[str, ...] = ()
    deterministic_constraints: tuple[str, ...] = ()
    material_actions: tuple[str, ...] = ()
    source_requirements: tuple[SourceRequirement, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    requires_reasoning: bool = False
    requires_research: bool = False
    requires_validation: bool = False
    requires_human_judgment: bool = False
    requires_connector: bool = False
    requires_tool_execution: bool = False
    research_domain: ResearchDomain | None = None
    ambiguity_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_research_domain(self) -> RequirementUnderstanding:
        if self.research_domain is not None and not self.requires_research:
            raise ValueError("research_domain requires requires_research=true")
        return self


class ImplementationDecision(BaseModel):
    """Auditable capability-first decision produced from structured facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    implementation_type: ImplementationType
    components: tuple[ImplementationType, ...] = ()
    reason: str = Field(min_length=10, max_length=2_000)
    required_capabilities: tuple[str, ...]
    required_tools: tuple[str, ...] = ()
    required_data: tuple[str, ...]
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    human_gate_required: bool
    missing_dependencies: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_composition(self) -> ImplementationDecision:
        if self.implementation_type == ImplementationType.COMPOSITE and len(self.components) < 2:
            raise ValueError("COMPOSITE decisions require at least two components")
        if self.implementation_type != ImplementationType.COMPOSITE and self.components:
            raise ValueError("components are only valid for COMPOSITE decisions")
        return self


class CapabilityDraft(BaseModel):
    """Governed generic DRAFT produced for every implementation decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_type: ImplementationType
    components: tuple[ImplementationType, ...] = ()
    purpose: str = Field(min_length=5, max_length=10_000)
    rationale: str = Field(min_length=10, max_length=2_000)
    required_capabilities: tuple[str, ...] = ()
    required_data: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    source_requirements: tuple[SourceRequirement, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    human_gate_required: bool
    test_requirements: tuple[str, ...] = ()
    ambiguity_notes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_composition(self) -> CapabilityDraft:
        if self.capability_type == ImplementationType.COMPOSITE and len(self.components) < 2:
            raise ValueError("COMPOSITE drafts require at least two components")
        if self.capability_type != ImplementationType.COMPOSITE and self.components:
            raise ValueError("components are only valid for COMPOSITE drafts")
        return self
