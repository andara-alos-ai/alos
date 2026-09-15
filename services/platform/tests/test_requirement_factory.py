from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alos.genesis.factory import RequirementAnalyzer
from alos.genesis.factory.models import (
    CapabilityDraft,
    ImplementationType,
    RequirementUnderstanding,
    SourceKind,
    SourceRequirement,
    TriggerKind,
)
from alos.genesis.factory.pipeline import (
    CapabilityProposalFactory,
    DependencyStatus,
    FactoryDependencyResolver,
)
from alos.genesis.factory.resolver import ImplementationTypeResolver
from alos.genesis.governed_foundations import ResearchDomain
from alos.runtime.agentic import (
    AgenticExecutionRequest,
    AgenticExecutionResult,
    ExecutionContext,
    ExecutionLimits,
    ExecutionMode,
    ExecutionStatus,
)


class SemanticEngine:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.requests: list[AgenticExecutionRequest] = []

    def execute(self, request: AgenticExecutionRequest) -> AgenticExecutionResult:
        self.requests.append(request)
        return AgenticExecutionResult(
            run_id=request.context.run_id,
            correlation_id=request.context.correlation_id,
            status=ExecutionStatus.SUCCEEDED,
            output=self.output,
        )

    def cancel(self, run_id: object) -> bool:
        return False


class EmptyCatalog:
    def resolve(self, request: object) -> object:
        return SimpleNamespace(
            resolved=[],
            missing_dependencies=list(request.capability_keys),  # type: ignore[attr-defined]
        )

    def list_tools(self, *, capability_key: str | None = None) -> list[object]:
        return []


def context() -> ExecutionContext:
    return ExecutionContext(
        organization_id=uuid4(),
        workspace_id=uuid4(),
        actor_user_id=uuid4(),
        actor_role="AI_ADMIN",
        agent_id=uuid4(),
        agent_version_id=uuid4(),
        run_id=uuid4(),
        correlation_id=uuid4(),
        execution_mode=ExecutionMode.TEST,
        classification="INTERNAL",
    )


def test_requirement_analyzer_uses_governed_structured_engine() -> None:
    output = {
        "objective": "Monitor records expiring within thirty days and assign owners.",
        "trigger_kind": "SCHEDULED",
        "required_capabilities": ["record expiry monitoring", "task assignment"],
        "required_data": ["record expiry date", "record owner"],
        "desired_outputs": ["finding", "task"],
        "material_actions": ["create task draft"],
        "evidence_requirements": ["source record and expiry date"],
        "requires_reasoning": False,
    }
    engine = SemanticEngine(output)

    understood = RequirementAnalyzer(engine).analyze(
        "Setiap hari monitor record yang akan kedaluwarsa dan buat task untuk owner.",
        context=context(),
        limits=ExecutionLimits(),
    )

    assert understood.trigger_kind == TriggerKind.SCHEDULED
    assert understood.required_capabilities == (
        "record expiry monitoring",
        "task assignment",
    )
    assert engine.requests[0].tools == ()


def test_resolver_does_not_create_agent_for_deterministic_approval_rule() -> None:
    requirement = RequirementUnderstanding(
        objective="Require human approval for transactions above a configured threshold.",
        trigger_kind=TriggerKind.CONDITIONAL,
        required_capabilities=("transaction threshold evaluation", "approval routing"),
        required_data=("transaction amount", "configured threshold"),
        desired_outputs=("approval request",),
        deterministic_constraints=("amount greater than configured threshold",),
        material_actions=("request approval",),
    )

    decision = ImplementationTypeResolver().resolve(requirement)

    assert decision.implementation_type == ImplementationType.COMPOSITE
    assert decision.components == (ImplementationType.RULE, ImplementationType.WORKFLOW)
    assert ImplementationType.AGENT not in decision.components
    assert decision.human_gate_required


def test_resolver_limits_agent_to_reasoning_inside_scheduled_composite() -> None:
    requirement = RequirementUnderstanding(
        objective="Analyze anomalies daily, create findings, and assign review tasks.",
        trigger_kind=TriggerKind.SCHEDULED,
        required_capabilities=("anomaly analysis", "finding creation", "task assignment"),
        required_data=("approved records",),
        desired_outputs=("finding", "task"),
        material_actions=("create finding draft", "create task draft"),
        requires_reasoning=True,
    )

    decision = ImplementationTypeResolver().resolve(requirement)

    assert decision.implementation_type == ImplementationType.COMPOSITE
    assert decision.components == (
        ImplementationType.AGENT,
        ImplementationType.WORKFLOW,
        ImplementationType.SCHEDULE,
    )
    assert decision.risk == "MEDIUM"


def test_resolver_uses_report_without_agent_for_research_only() -> None:
    requirement = RequirementUnderstanding(
        objective="Research approved evidence and produce a cited market report.",
        trigger_kind=TriggerKind.MANUAL,
        desired_outputs=("research report",),
        requires_research=True,
        research_domain=ResearchDomain.PROPERTY_MARKET,
    )

    decision = ImplementationTypeResolver().resolve(requirement)

    assert decision.implementation_type == ImplementationType.REPORT
    assert ImplementationType.AGENT not in decision.components


def test_resolver_combines_agent_and_report_only_when_research_requires_reasoning() -> None:
    requirement = RequirementUnderstanding(
        objective="Reason across conflicting evidence and produce a research report.",
        trigger_kind=TriggerKind.MANUAL,
        desired_outputs=("research report",),
        requires_research=True,
        requires_reasoning=True,
        research_domain=ResearchDomain.TECHNOLOGY,
    )

    decision = ImplementationTypeResolver().resolve(requirement)

    assert decision.implementation_type == ImplementationType.COMPOSITE
    assert set(decision.components) == {ImplementationType.AGENT, ImplementationType.REPORT}


def test_resolver_combines_agent_and_schedule_for_scheduled_reasoning() -> None:
    requirement = RequirementUnderstanding(
        objective="Reason over approved records on a governed daily schedule.",
        trigger_kind=TriggerKind.SCHEDULED,
        requires_reasoning=True,
    )

    decision = ImplementationTypeResolver().resolve(requirement)

    assert decision.components == (ImplementationType.AGENT, ImplementationType.SCHEDULE)


@pytest.mark.parametrize("kind", [SourceKind.INTERNAL, SourceKind.EXTERNAL])
def test_requirement_understanding_records_source_semantics(kind: SourceKind) -> None:
    source = SourceRequirement(
        kind=kind,
        purpose="Provide evidence for the governed research report.",
        provenance_required=True,
        citation_required=True,
        freshness_required=True,
        reliability_required=True,
    )

    requirement = RequirementUnderstanding(
        objective="Research evidence from the explicitly requested source boundary.",
        trigger_kind=TriggerKind.MANUAL,
        source_requirements=(source,),
        requires_research=True,
    )

    assert requirement.source_requirements[0].kind == kind


@pytest.mark.parametrize("domain", list(ResearchDomain))
def test_official_research_domains_are_valid(domain: ResearchDomain) -> None:
    requirement = RequirementUnderstanding(
        objective="Produce a governed research report for the selected official domain.",
        trigger_kind=TriggerKind.MANUAL,
        requires_research=True,
        research_domain=domain,
    )

    assert requirement.research_domain == domain


def test_invalid_research_domain_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RequirementUnderstanding(
            objective="Produce research for an unsupported taxonomy domain.",
            trigger_kind=TriggerKind.MANUAL,
            requires_research=True,
            research_domain="UNSUPPORTED",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("capability_type", list(ImplementationType))
def test_generic_draft_represents_every_implementation_type(
    capability_type: ImplementationType,
) -> None:
    components = (
        (ImplementationType.RULE, ImplementationType.WORKFLOW)
        if capability_type == ImplementationType.COMPOSITE
        else ()
    )

    draft = CapabilityDraft(
        capability_type=capability_type,
        components=components,
        purpose="Represent a governed generic capability proposal.",
        rationale="The selected capability type matches the structured requirement.",
        risk="LOW",
        human_gate_required=False,
    )

    assert draft.capability_type == capability_type


def test_non_agent_requirement_always_produces_generic_draft() -> None:
    requirement = RequirementUnderstanding(
        objective="Enforce deterministic approval and route a human approval request.",
        trigger_kind=TriggerKind.CONDITIONAL,
        deterministic_constraints=("amount exceeds configured threshold",),
        material_actions=("request approval",),
    )
    decision = ImplementationTypeResolver().resolve(requirement)
    resolution = FactoryDependencyResolver(EmptyCatalog()).resolve(())  # type: ignore[arg-type]

    proposal = CapabilityProposalFactory().create(
        requirement,
        decision,
        resolution,
        agent_key="NOT_AN_AGENT",
        name="Deterministic Approval",
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
    )

    assert proposal.draft.capability_type == ImplementationType.COMPOSITE
    assert proposal.draft.components == (ImplementationType.RULE, ImplementationType.WORKFLOW)
    assert proposal.agent_contract is None
    assert proposal.lifecycle_status == "DRAFT"


def test_agent_requirement_produces_generic_draft_and_agent_contract() -> None:
    requirement = RequirementUnderstanding(
        objective="Reason over approved evidence while preserving governed source lineage.",
        trigger_kind=TriggerKind.MANUAL,
        requires_reasoning=True,
        evidence_requirements=("source lineage",),
    )
    decision = ImplementationTypeResolver().resolve(requirement)
    resolution = FactoryDependencyResolver(EmptyCatalog()).resolve(())  # type: ignore[arg-type]

    proposal = CapabilityProposalFactory().create(
        requirement,
        decision,
        resolution,
        agent_key="GOVERNED_REASONER",
        name="Governed Reasoner",
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
    )

    assert proposal.draft.capability_type == ImplementationType.AGENT
    assert proposal.agent_contract is not None


def test_resolver_represents_unresolved_connector_and_tool_without_inventing_authority() -> None:
    requirement = RequirementUnderstanding(
        objective="Use an approved external connector and tool execution path.",
        trigger_kind=TriggerKind.MANUAL,
        requires_connector=True,
        requires_tool_execution=True,
    )
    decision = ImplementationTypeResolver().resolve(requirement)
    resolution = FactoryDependencyResolver(EmptyCatalog()).resolve(  # type: ignore[arg-type]
        (),
        requires_connector=requirement.requires_connector,
        requires_tool_execution=requirement.requires_tool_execution,
    )

    assert decision.components == (
        ImplementationType.CONNECTOR_REQUIREMENT,
        ImplementationType.TOOL_REQUIREMENT,
    )
    assert resolution.tool_keys == ()
    assert resolution.permission_keys == ()
    assert {item.kind for item in resolution.missing_dependencies} == {"CONNECTOR", "TOOL"}
    assert resolution.readiness == DependencyStatus.NEEDS_IMPLEMENTATION
