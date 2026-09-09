"""Governed memory, skills, delegation, and generic R&D domain foundations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    workspace_id: UUID
    division_id: UUID | None = None
    project_id: UUID | None = None
    tenant_id: UUID | None = None

    def contains(self, other: Scope) -> bool:
        return all(
            parent is None or parent == child
            for parent, child in (
                (self.organization_id, other.organization_id),
                (self.workspace_id, other.workspace_id),
                (self.division_id, other.division_id),
                (self.project_id, other.project_id),
                (self.tenant_id, other.tenant_id),
            )
        )


class MemoryKind(StrEnum):
    WORKING = "WORKING"
    CONVERSATION = "CONVERSATION"
    PROJECT = "PROJECT"
    DIVISION_KNOWLEDGE = "DIVISION_KNOWLEDGE"
    ORGANIZATION_KNOWLEDGE = "ORGANIZATION_KNOWLEDGE"
    AGENT_OPERATIONAL = "AGENT_OPERATIONAL"
    LEARNED_KNOWLEDGE = "LEARNED_KNOWLEDGE"


class ScopedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: UUID
    kind: MemoryKind
    scope: Scope
    classification: str
    content_digest: str = Field(pattern="^[a-f0-9]{64}$")
    source_reference: str = Field(min_length=1)
    lineage: dict[str, Any]
    retention_until: AwareDatetime
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_retention(self) -> ScopedMemory:
        if self.retention_until <= self.created_at:
            raise ValueError("memory retention must end after creation")
        return self


class SkillStatus(StrEnum):
    PROPOSED = "PROPOSED"
    DRAFT = "DRAFT"
    TEST = "TEST"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


_SKILL_TRANSITIONS = {
    SkillStatus.PROPOSED: {SkillStatus.DRAFT},
    SkillStatus.DRAFT: {SkillStatus.TEST},
    SkillStatus.TEST: {SkillStatus.REVIEW},
    SkillStatus.REVIEW: {SkillStatus.APPROVED, SkillStatus.DRAFT},
    SkillStatus.APPROVED: {SkillStatus.ACTIVE},
    SkillStatus.ACTIVE: {SkillStatus.DEPRECATED},
    SkillStatus.DEPRECATED: set(),
}


def validate_skill_transition(current: SkillStatus, target: SkillStatus) -> None:
    if target not in _SKILL_TRANSITIONS[current]:
        raise ValueError(f"invalid skill lifecycle transition: {current} -> {target}")


class DelegationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parent_run_id: UUID
    child_agent_version_id: UUID
    parent_scope: Scope
    child_scope: Scope
    active_child: bool
    delegation_depth: int = Field(ge=0)
    active_subagents: int = Field(ge=0)
    remaining_cost_budget: float = Field(ge=0)
    lineage_agent_version_ids: tuple[UUID, ...]


def validate_delegation(
    request: DelegationRequest,
    *,
    max_depth: int,
    max_subagents: int,
) -> None:
    if not request.active_child:
        raise ValueError("delegated Agent Version must be ACTIVE")
    if not request.parent_scope.contains(request.child_scope):
        raise ValueError("delegation would widen data scope")
    if request.delegation_depth >= max_depth:
        raise ValueError("delegation depth limit reached")
    if request.active_subagents >= max_subagents:
        raise ValueError("subagent limit reached")
    if request.remaining_cost_budget <= 0:
        raise ValueError("delegation cost budget exhausted")
    if request.child_agent_version_id in request.lineage_agent_version_ids:
        raise ValueError("circular delegation is forbidden")


class ResearchStatus(StrEnum):
    REQUEST = "REQUEST"
    SCOPING = "SCOPING"
    RESEARCH = "RESEARCH"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    ANALYSIS = "ANALYSIS"
    FINDINGS = "FINDINGS"
    RECOMMENDATION = "RECOMMENDATION"
    EXPERIMENT = "EXPERIMENT"
    EVALUATION = "EVALUATION"
    REVIEW = "REVIEW"
    DECISION = "DECISION"
    CLOSED = "CLOSED"


class ResearchProject(BaseModel):
    """Domain-neutral research record; no technology-specific fields are required."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    research_id: UUID
    scope: Scope
    research_type: str
    domain: str
    title: str
    objective: str
    questions: tuple[str, ...]
    status: ResearchStatus = ResearchStatus.REQUEST
    methods: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    evidence_ids: tuple[UUID, ...] = ()
    findings: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    impact: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None
    experiment_plan: dict[str, Any] | None = None
    evaluation_plan: dict[str, Any] | None = None
    decision_required: bool = True
    decision_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    def factory_requirement(self) -> str:
        if self.status not in {ResearchStatus.DECISION, ResearchStatus.CLOSED}:
            raise ValueError("research must reach a governed decision before factory handoff")
        if self.decision_required and self.decision_id is None:
            raise ValueError("human decision is required before factory handoff")
        if not self.recommendation:
            raise ValueError("research has no recommendation to hand off")
        return self.recommendation
