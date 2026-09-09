from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alos.genesis.governed_foundations import (
    DelegationRequest,
    MemoryKind,
    ResearchProject,
    ResearchStatus,
    Scope,
    ScopedMemory,
    SkillStatus,
    validate_delegation,
    validate_skill_transition,
)


def scope(**values: object) -> Scope:
    data = {"organization_id": uuid4(), "workspace_id": uuid4()}
    data.update(values)
    return Scope(**data)


def test_memory_requires_lineage_scope_and_future_retention() -> None:
    now = datetime.now(UTC)
    memory = ScopedMemory(
        memory_id=uuid4(),
        kind=MemoryKind.PROJECT,
        scope=scope(project_id=uuid4()),
        classification="INTERNAL",
        content_digest="a" * 64,
        source_reference="document-version:1",
        lineage={"document_id": str(uuid4())},
        created_at=now,
        retention_until=now + timedelta(days=30),
    )
    assert memory.source_reference
    with pytest.raises(ValidationError):
        ScopedMemory.model_validate(
            {**memory.model_dump(), "retention_until": now - timedelta(days=1)}
        )


def test_skill_cannot_skip_review_and_approval() -> None:
    validate_skill_transition(SkillStatus.PROPOSED, SkillStatus.DRAFT)
    with pytest.raises(ValueError, match="invalid skill"):
        validate_skill_transition(SkillStatus.DRAFT, SkillStatus.ACTIVE)


def test_delegation_denies_cycle_and_scope_widening() -> None:
    parent = scope(project_id=uuid4())
    child_id = uuid4()
    request = DelegationRequest(
        parent_run_id=uuid4(),
        child_agent_version_id=child_id,
        parent_scope=parent,
        child_scope=Scope(
            organization_id=parent.organization_id,
            workspace_id=parent.workspace_id,
        ),
        active_child=True,
        delegation_depth=0,
        active_subagents=0,
        remaining_cost_budget=1,
        lineage_agent_version_ids=(child_id,),
    )
    with pytest.raises(ValueError):
        validate_delegation(request, max_depth=1, max_subagents=1)


def test_research_is_generic_and_requires_decision_before_factory_handoff() -> None:
    now = datetime.now(UTC)
    research = ResearchProject(
        research_id=uuid4(),
        scope=scope(),
        research_type="COMPARATIVE",
        domain="customer_experience",
        title="Reduce process cost",
        objective="Compare methods to reduce process cost without lowering quality.",
        questions=("Which alternative has the best evidence-adjusted impact?",),
        status=ResearchStatus.RECOMMENDATION,
        recommendation="Create a reusable validation capability.",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(ValueError, match="decision"):
        research.factory_requirement()
    decided = research.model_copy(
        update={"status": ResearchStatus.DECISION, "decision_id": uuid4()}
    )
    assert decided.factory_requirement() == "Create a reusable validation capability."
