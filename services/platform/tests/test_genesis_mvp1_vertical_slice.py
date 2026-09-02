"""End-to-end safety test for the GENESIS MVP1 CREATE-to-RUN vertical slice."""

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from alos.agents.capabilities import CapabilityRegistry
from alos.agents.contract import AgentDefinition, AgentKind, AgentReference, AgentStatus
from alos.agents.registry import AgentRegistry, RegistryError
from alos.agents.runtime import (
    AgentCapabilityExecuteRequest,
    AgentLifecycleService,
    AgentRunRequest,
    RuntimePolicyViolation,
    SharedAgentRuntime,
)
from alos.agents.runtime.application import AgentCapabilityService
from alos.genesis import GenesisDesignService, GenesisPipelineService, SourceRegistry
from alos.genesis.models import (
    GenesisReviewCreate,
    GenesisReviewDecision,
    GenesisReviewGate,
    GenesisStrategy,
    GenesisSubmitRequest,
)
from alos.genesis.repository import InMemoryGenesisStore
from alos.security import Principal, Role
from alos.security.authorization import AuthorizationDenied
from alos.tools import ToolRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_REFERENCE = "ALOS-SP-SYNTHETIC-PILOT@1.0.0"
DIVISIONS = ("FINANCE", "SALES_MARKETING", "PROPERTY", "HR", "LEGAL", "IT")


def _principal(
    organization_id: object, role: Role, division_codes: tuple[str, ...] = ()
) -> Principal:
    return Principal(
        user_id=uuid4(),
        organization_id=organization_id,
        roles=frozenset({role}),
        division_codes=frozenset(division_codes),
    )


def _daily_brief_contract(
    *,
    version: str = "0.1.0",
    extends: AgentReference | None = None,
) -> AgentDefinition:
    return AgentDefinition(
        contract_version="1.0.0",
        agent_id="MVP1_E2E_DAILY",
        name="MVP1 End-to-End Daily Brief Agent",
        agent_kind=AgentKind.LOGICAL,
        domain="shared-enterprise",
        division_scope=DIVISIONS,
        purpose=(
            "Menyusun ringkasan harian berbasis fakta sintetis terverifikasi "
            "dengan citation yang dapat ditelusuri."
        ),
        human_owner="AI Executive Operating Layer",
        triggers=("ON_DEMAND",),
        inputs=("synthetic_source_record", "workspace_context"),
        source_of_truth=("Registered synthetic source",),
        capabilities=("aggregate_verified_facts",),
        outputs=("structured_result", "citation_references"),
        tools_allowed=("alos.audit.read",),
        approval_boundary=("Human review is required before any material action",),
        evidence_requirement=("Every result references registered source evidence",),
        forbidden_actions=(
            "write production data",
            "approve its own release",
            "create or modify a tool",
        ),
        metrics=("citation coverage", "test pass rate", "cost per run"),
        escalation=("Escalate blocked results to the domain owner",),
        prompt_ref="genesis.validation@0.1.0",
        model_policy_ref="openai-primary-claude-fallback@0.1.0",
        permission_policy_ref="read-only-evidence@0.1.0",
        risk_level="LOW",
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={"type": "object", "additionalProperties": False},
        extends=extends,
        rollback_target=extends,
        version=version,
        status=AgentStatus.DRAFT,
    )


def _release(
    service: GenesisPipelineService,
    candidate: AgentDefinition,
    strategy: GenesisStrategy,
    requester: Principal,
    business: Principal,
    technical: Principal,
    releaser: Principal,
    base: AgentReference | None = None,
) -> None:
    submitted = service.submit(
        GenesisSubmitRequest(
            strategy=strategy,
            justification="Membuat kontrak logical agent MVP1 dengan data sintetis.",
            source_references=(SOURCE_REFERENCE,),
            candidate=candidate,
            base=base,
        ),
        requester,
    )
    service.review(
        submitted.request_id,
        GenesisReviewCreate(
            gate=GenesisReviewGate.BUSINESS,
            decision=GenesisReviewDecision.APPROVED,
            notes="Owner bisnis menyetujui scope, evidence, dan KPI sintetis.",
        ),
        business,
    )
    service.review(
        submitted.request_id,
        GenesisReviewCreate(
            gate=GenesisReviewGate.TECHNICAL,
            decision=GenesisReviewDecision.APPROVED,
            notes="IT menyetujui contract, tool allowlist, dan pengujian sintetis.",
        ),
        technical,
    )
    service.stage(submitted.request_id, technical)
    released = service.release(submitted.request_id, releaser)
    assert released.production_effect is False
    assert released.status == "RELEASED"


def test_genesis_creates_reviews_releases_runs_suspends_and_rolls_back_agent(
    tmp_path: Path,
) -> None:
    definitions = tmp_path / "definitions"
    shutil.copytree(REPOSITORY_ROOT / "definitions", definitions)
    registry = AgentRegistry(definitions)
    service = GenesisPipelineService(
        GenesisDesignService(registry),
        CapabilityRegistry(definitions),
        InMemoryGenesisStore(),
        SourceRegistry(definitions),
        registry,
    )
    organization_id = uuid4()
    requester = _principal(organization_id, Role.AI_EXECUTIVE)
    business = _principal(organization_id, Role.DIRECTOR)
    technical = _principal(organization_id, Role.IT_ADMIN)
    releaser = _principal(organization_id, Role.DIRECTOR)

    _release(
        service,
        _daily_brief_contract(),
        GenesisStrategy.CREATE,
        requester,
        business,
        technical,
        releaser,
    )
    assert registry.get("MVP1_E2E_DAILY", "0.1.0").status == AgentStatus.RELEASED
    assert registry.activate_generated("MVP1_E2E_DAILY", "0.1.0").status == AgentStatus.ACTIVE

    runtime = SharedAgentRuntime(registry, ToolRegistry(definitions))
    plan = runtime.prepare(
        AgentRunRequest(
            agent_id="MVP1_E2E_DAILY",
            agent_version="0.1.0",
            capability="aggregate_verified_facts",
            input_references=["synthetic-source:daily-001"],
            requested_tools=["alos.audit.read"],
            correlation_id=uuid4(),
            idempotency_key="mvp1-e2e-daily-run-001",
        )
    )
    executed = runtime.execute(
        plan,
        {
            "verified_facts": [{"division": "FINANCE", "status": "ON_TRACK"}],
            "source_references": ["synthetic-source:daily-001"],
        },
    )
    assert executed.execution is not None
    assert executed.execution.status == "NEEDS_REVIEW"
    assert executed.execution.output_reference["fact_count"] == 1

    with pytest.raises(RuntimePolicyViolation, match="Tool tidak diizinkan"):
        runtime.prepare(
            AgentRunRequest(
                agent_id="MVP1_E2E_DAILY",
                agent_version="0.1.0",
                capability="aggregate_verified_facts",
                input_references=["synthetic-source:denied-tool"],
                requested_tools=["alos.evidence.read"],
                correlation_id=uuid4(),
                idempotency_key="mvp1-e2e-denied-tool-001",
            )
        )

    assert registry.suspend_generated("MVP1_E2E_DAILY", "0.1.0").status == AgentStatus.SUSPENDED
    with pytest.raises(RuntimePolicyViolation, match="tidak dapat dijalankan"):
        runtime.prepare(
            AgentRunRequest(
                agent_id="MVP1_E2E_DAILY",
                agent_version="0.1.0",
                capability="aggregate_verified_facts",
                input_references=["synthetic-source:suspended"],
                requested_tools=["alos.audit.read"],
                correlation_id=uuid4(),
                idempotency_key="mvp1-e2e-suspended-run-001",
            )
        )

    registry.activate_generated("MVP1_E2E_DAILY", "0.1.0")
    first_version = AgentReference(agent_id="MVP1_E2E_DAILY", version="0.1.0")
    _release(
        service,
        _daily_brief_contract(version="0.2.0", extends=first_version),
        GenesisStrategy.EXTEND,
        requester,
        business,
        technical,
        releaser,
        first_version,
    )
    registry.activate_generated("MVP1_E2E_DAILY", "0.2.0")
    assert registry.get("MVP1_E2E_DAILY", "0.1.0").status == AgentStatus.ROLLED_BACK
    restored = registry.rollback_generated("MVP1_E2E_DAILY", "0.2.0", first_version)
    assert restored.status == AgentStatus.ACTIVE
    assert registry.get("MVP1_E2E_DAILY", "0.2.0").status == AgentStatus.ROLLED_BACK
    assert registry.get("MVP1_E2E_DAILY").version == "0.1.0"


def test_lifecycle_control_requires_human_it_operator_and_writes_audit_event(
    tmp_path: Path,
) -> None:
    definitions = tmp_path / "definitions"
    shutil.copytree(REPOSITORY_ROOT / "definitions", definitions)
    registry = AgentRegistry(definitions)
    registry.release_generated(_daily_brief_contract())
    audit_events: list[tuple[str, str, str]] = []

    class AuditStore:
        def record_standalone_agent_run(self, *_args: object) -> None:
            raise AssertionError("lifecycle test must not record an agent run")

        def record_agent_lifecycle_transition(
            self,
            before: AgentDefinition,
            after: AgentDefinition,
            _principal: Principal,
            action: str,
            reason: str,
            _correlation_id: object,
        ) -> None:
            audit_events.append((action, before.status.value, after.status.value))
            assert reason == "Synthetic kill-switch verification."

    organization_id = uuid4()
    service = AgentLifecycleService(registry, AuditStore())
    operator = _principal(organization_id, Role.IT_ADMIN)
    activated = service.activate(
        "MVP1_E2E_DAILY",
        "0.1.0",
        operator,
        "Synthetic kill-switch verification.",
    )
    suspended = service.suspend(
        "MVP1_E2E_DAILY",
        "0.1.0",
        operator,
        "Synthetic kill-switch verification.",
    )

    assert activated.status == AgentStatus.ACTIVE
    assert suspended.status == AgentStatus.SUSPENDED
    assert audit_events == [
        ("agent.activated", "RELEASED", "ACTIVE"),
        ("agent.suspended", "ACTIVE", "SUSPENDED"),
    ]


def test_logical_agent_rejects_missing_or_overbroad_configuration_policy(tmp_path: Path) -> None:
    definitions = tmp_path / "definitions"
    shutil.copytree(REPOSITORY_ROOT / "definitions", definitions)
    registry = AgentRegistry(definitions)

    with pytest.raises(RegistryError, match="Model policy tidak terdaftar"):
        registry.validate_candidate(
            _daily_brief_contract().model_copy(
                update={"model_policy_ref": "unknown-policy@0.1.0"}
            )
        )
    with pytest.raises(RegistryError, match="Referensi Tool Registry tidak valid"):
        registry.validate_candidate(
            _daily_brief_contract().model_copy(
                update={"tools_allowed": ("alos.approval.create",)}
            )
        )


@pytest.mark.parametrize(
    ("division", "role"),
    (
        ("FINANCE", Role.FINANCE),
        ("SALES_MARKETING", Role.SALES),
        ("PROPERTY", Role.PROPERTY),
        ("HR", Role.HR),
        ("LEGAL", Role.LEGAL),
        ("IT", Role.IT_ADMIN),
    ),
)
def test_daily_brief_runs_in_each_mvp1_division_context(
    division: str, role: Role
) -> None:
    class RunStore:
        def __init__(self) -> None:
            self.run_ids: list[object] = []

        def record_standalone_agent_run(self, plan: object, *_args: object) -> None:
            self.run_ids.append(plan)

        def record_agent_lifecycle_transition(self, *_args: object) -> None:
            raise AssertionError("division UAT must not change lifecycle state")

    registry = AgentRegistry(REPOSITORY_ROOT / "definitions")
    runtime = SharedAgentRuntime(registry, ToolRegistry(REPOSITORY_ROOT / "definitions"))
    store = RunStore()
    service = AgentCapabilityService(
        registry,
        CapabilityRegistry(REPOSITORY_ROOT / "definitions"),
        runtime,
        store,
    )
    result = service.execute(
        AgentCapabilityExecuteRequest(
            agent_id="DAILY_BRIEF",
            capability="aggregate_verified_facts",
            input_references=[f"synthetic:{division.lower()}"],
            requested_tools=["alos.audit.read"],
            input_payload={
                "verified_facts": [{"division": division, "status": "ON_TRACK"}],
                "source_references": [f"synthetic:{division.lower()}"],
            },
        ),
        _principal(uuid4(), role, (division,)),
        f"uat-{division.lower()}-daily-001",
    )

    assert result.agent_id == "DAILY_BRIEF"
    assert result.output_reference["fact_count"] == 1
    assert store.run_ids


def test_permit_monitor_denies_unauthorized_division_context() -> None:
    registry = AgentRegistry(REPOSITORY_ROOT / "definitions")
    runtime = SharedAgentRuntime(registry, ToolRegistry(REPOSITORY_ROOT / "definitions"))

    class RunStore:
        def record_standalone_agent_run(self, *_args: object) -> None:
            raise AssertionError("run must not be recorded after scope denial")

        def record_agent_lifecycle_transition(self, *_args: object) -> None:
            raise AssertionError("scope denial must not change lifecycle state")

    service = AgentCapabilityService(
        registry,
        CapabilityRegistry(REPOSITORY_ROOT / "definitions"),
        runtime,
        RunStore(),
    )
    with pytest.raises(AuthorizationDenied, match="konteks divisi"):
        service.execute(
            AgentCapabilityExecuteRequest(
                agent_id="PERMIT_OVERDUE_MONITOR",
                capability="monitor_capa_deadline",
                input_references=["synthetic:finance-permit"],
                requested_tools=["alos.legal.read"],
                input_payload={"due_dates": ["2026-09-01T00:00:00Z"]},
            ),
            _principal(uuid4(), Role.FINANCE, ("FINANCE",)),
            "uat-finance-permit-denied-001",
        )
