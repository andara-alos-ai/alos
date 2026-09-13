"""Typed domain models shared across the GENESIS factory pipeline."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    evidence_requirements: tuple[str, ...] = ()
    requires_reasoning: bool = False
    requires_research: bool = False
    requires_validation: bool = False
    requires_human_judgment: bool = False
    ambiguity_notes: tuple[str, ...] = ()


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
