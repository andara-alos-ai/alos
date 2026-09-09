from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from alos.capabilities.registry import CapabilityRecord, TypedToolRecord
from alos.genesis.factory.models import (
    ImplementationDecision,
    ImplementationType,
    RequirementUnderstanding,
    TriggerKind,
)
from alos.genesis.factory.pipeline import (
    AgentContractFactory,
    DependencyStatus,
    FactoryDependencyResolver,
)


def capability(
    key: str,
    *,
    tools: list[str],
    availability: str = "AVAILABLE",
    configuration: str = "CONFIGURED",
) -> CapabilityRecord:
    now = datetime.now(UTC)
    return CapabilityRecord(
        capability_key=key,
        domain="records",
        name=key,
        description="Reusable test capability.",
        supported_scopes=["PROJECT"],
        allowed_data_classification=["INTERNAL"],
        risk_level="LOW",
        access_mode="READ",
        availability=availability,
        configuration_status=configuration,
        version=1,
        metadata={},
        backing_tools=tools,
        created_at=now,
        updated_at=now,
    )


def tool(key: str, capability_key: str) -> TypedToolRecord:
    return TypedToolRecord(
        tool_key=key,
        capability_key=capability_key,
        description="Governed test tool.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_level="LOW",
        allowed_scopes=["PROJECT"],
        required_permission=key,
        access_mode="READ",
        timeout_seconds=10,
        idempotency_policy="NONE",
        audit_policy="ALWAYS",
        runtime_handler="RECORD_READ",
        lifecycle_status="APPROVED",
        version=1,
    )


class Catalog:
    def __init__(self, capabilities: list[CapabilityRecord], tools: list[TypedToolRecord]):
        self.capabilities = capabilities
        self.tools = tools

    def resolve(self, request: object) -> object:
        requested = request.capability_keys  # type: ignore[attr-defined]
        found = [item for item in self.capabilities if item.capability_key in requested]
        return SimpleNamespace(
            resolved=found,
            missing_dependencies=[
                key for key in requested if key not in {x.capability_key for x in found}
            ],
        )

    def list_tools(self, *, capability_key: str | None = None) -> list[TypedToolRecord]:
        return self.tools


def understanding() -> RequirementUnderstanding:
    return RequirementUnderstanding(
        objective="Analyze expiring records, create findings, and prepare owner tasks daily.",
        trigger_kind=TriggerKind.SCHEDULED,
        required_capabilities=("records.expiry.read", "finding.create"),
        required_data=("expiry date", "owner"),
        desired_outputs=("finding", "task"),
        material_actions=("create finding draft",),
        evidence_requirements=("source record",),
        requires_reasoning=True,
    )


def decision() -> ImplementationDecision:
    return ImplementationDecision(
        implementation_type=ImplementationType.COMPOSITE,
        components=(
            ImplementationType.AGENT,
            ImplementationType.WORKFLOW,
            ImplementationType.SCHEDULE,
        ),
        reason="Reasoning is isolated while schedule and writes remain governed primitives.",
        required_capabilities=understanding().required_capabilities,
        required_data=understanding().required_data,
        risk="MEDIUM",
        human_gate_required=True,
    )


def test_factory_resolves_registered_capabilities_tools_and_permissions() -> None:
    catalog = Catalog(
        [
            capability("records.expiry.read", tools=["records.expiry.read"]),
            capability("finding.create", tools=["finding.create"]),
        ],
        [
            tool("records.expiry.read", "records.expiry.read"),
            tool("finding.create", "finding.create"),
        ],
    )

    resolution = FactoryDependencyResolver(catalog).resolve(
        understanding().required_capabilities
    )
    proposal = AgentContractFactory().create(
        understanding(),
        decision(),
        resolution,
        agent_key="GENERIC_EXPIRY_MONITOR",
        name="Generic Expiry Monitor",
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
    )

    assert resolution.readiness == DependencyStatus.AVAILABLE
    assert resolution.tool_keys == ("records.expiry.read", "finding.create")
    assert proposal.lifecycle_status == "DRAFT"
    assert proposal.agent_contract is not None
    assert proposal.agent_contract.model_policy["execution_engine"] == "PYDANTICAI"
    assert proposal.agent_contract.approval_required
    assert {test.category for test in proposal.tests} >= {
        "POSITIVE",
        "NEGATIVE",
        "REGRESSION",
        "SECURITY",
        "RECOVERY",
        "PERMISSION",
        "TENANT_ISOLATION",
        "TOOL_DENIAL",
        "BUDGET",
        "SOURCE_VALIDATION",
        "EVIDENCE",
    }


def test_missing_capability_is_needs_implementation_not_fake_configuration() -> None:
    resolution = FactoryDependencyResolver(Catalog([], [])).resolve(("records.expiry.read",))

    assert resolution.readiness == DependencyStatus.NEEDS_IMPLEMENTATION
    assert resolution.missing_dependencies[0].status == DependencyStatus.NEEDS_IMPLEMENTATION


def test_registered_unconfigured_capability_is_needs_configuration() -> None:
    catalog = Catalog(
        [
            capability(
                "records.expiry.read",
                tools=[],
                availability="UNAVAILABLE",
                configuration="NEEDS_CONFIGURATION",
            )
        ],
        [],
    )

    resolution = FactoryDependencyResolver(catalog).resolve(("records.expiry.read",))

    assert resolution.readiness == DependencyStatus.NEEDS_CONFIGURATION


def test_non_agent_decision_generates_configuration_without_agent_contract() -> None:
    requirement = RequirementUnderstanding(
        objective="Enforce a configured transaction approval threshold.",
        trigger_kind=TriggerKind.CONDITIONAL,
        required_capabilities=("approval.request",),
        required_data=("amount", "threshold"),
        deterministic_constraints=("amount above threshold",),
        material_actions=("request approval",),
    )
    non_agent = ImplementationDecision(
        implementation_type=ImplementationType.COMPOSITE,
        components=(ImplementationType.RULE, ImplementationType.WORKFLOW),
        reason="A deterministic rule and governed workflow are sufficient for this requirement.",
        required_capabilities=requirement.required_capabilities,
        required_data=requirement.required_data,
        risk="MEDIUM",
        human_gate_required=True,
    )
    resolution = FactoryDependencyResolver(Catalog([], [])).resolve(
        requirement.required_capabilities
    )

    proposal = AgentContractFactory().create(
        requirement,
        non_agent,
        resolution,
        agent_key="NOT_USED_AGENT_KEY",
        name="Not an Agent",
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
    )

    assert proposal.agent_contract is None
