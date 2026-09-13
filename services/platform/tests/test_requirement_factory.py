from uuid import uuid4

from alos.genesis.factory import RequirementAnalyzer
from alos.genesis.factory.models import (
    ImplementationType,
    RequirementUnderstanding,
    TriggerKind,
)
from alos.genesis.factory.resolver import ImplementationTypeResolver
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
