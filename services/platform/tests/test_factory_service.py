from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from alos.genesis.factory.models import RequirementUnderstanding, TriggerKind
from alos.genesis.factory.persistence import (
    FactoryRequestCreate,
    FactoryRequestRecord,
    FactoryStatus,
)
from alos.genesis.factory.pipeline import FactoryDependencyResolver
from alos.genesis.factory.service import GenesisFactoryService
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.runtime.agentic import ExecutionLimits
from alos.security.tokens import ActorContext


class Analyzer:
    def analyze(self, requirement, *, context, limits):
        return RequirementUnderstanding(
            objective=requirement,
            trigger_kind=TriggerKind.SCHEDULED,
            required_capabilities=(),
            required_data=("approved records",),
            desired_outputs=("finding", "task"),
            material_actions=("create draft task",),
            evidence_requirements=("source record",),
            requires_reasoning=True,
        )


class Catalog:
    def resolve(self, request):
        return SimpleNamespace(resolved=[], missing_dependencies=[])

    def list_tools(self, *, capability_key=None):
        return []


class Repository:
    def __init__(self, record):
        self.record = record

    def begin_analysis(self, request_id, actor, *, correlation_id):
        self.record = self.record.model_copy(update={"status": FactoryStatus.ANALYZING})
        return self.record

    def complete_analysis(
        self,
        request_id,
        actor,
        *,
        understanding,
        decision,
        proposal,
        agent_contract_id,
        agent_version_id,
        correlation_id,
    ):
        self.record = self.record.model_copy(
            update={
                "status": FactoryStatus.DRAFT,
                "requirement_understanding": understanding,
                "implementation_decision": decision,
                "dependency_resolution": proposal.resolution,
                "factory_proposal": proposal,
            }
        )
        return self.record

    def link_governance(
        self,
        request_id,
        actor,
        *,
        agent_contract_id,
        agent_version_id,
        release_change_request_id,
        correlation_id,
    ):
        self.record = self.record.model_copy(
            update={
                "agent_contract_id": agent_contract_id,
                "agent_version_id": agent_version_id,
                "release_change_request_id": release_change_request_id,
            }
        )
        return self.record

    def fail_analysis(self, *args, **kwargs):
        raise AssertionError("successful orchestration must not persist a blocker")


class Registry:
    def __init__(self):
        self.contract = None

    def create_draft(self, contract, **kwargs):
        self.contract = contract
        return SimpleNamespace(
            agent_contract_id=uuid4(),
            agent_version_id=uuid4(),
            agent_key=contract.agent_key,
        )


class Releases:
    def __init__(self):
        self.tests = []
        self.change_request_id = uuid4()

    def create_release_request(self, *args, **kwargs):
        return SimpleNamespace(change_request_id=self.change_request_id)

    def register_test_case(self, change_request_id, request, **kwargs):
        self.tests.append(request)


def _actor(workspace_id, organization_id, user_id):
    now = datetime.now(UTC)
    return ActorContext(
        user_id=user_id,
        organization_id=organization_id,
        roles=[HumanRole.DIRECTOR],
        division_codes=[DivisionCode.IT],
        workspace_ids=[workspace_id],
        data_scope=DataScope.COMPANY,
        permissions=[],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_factory_service_persists_and_links_agent_to_existing_governance() -> None:
    workspace_id, organization_id, user_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    record = FactoryRequestRecord(
        factory_request_id=uuid4(),
        organization_id=organization_id,
        workspace_id=workspace_id,
        division_id=None,
        project_id=None,
        tenant_id=None,
        requirement="Analyze approved records daily, create findings, and prepare owner tasks.",
        source_type="DIRECT",
        source_research_id=None,
        status=FactoryStatus.REQUEST,
        requirement_understanding=None,
        implementation_decision=None,
        dependency_resolution=None,
        factory_proposal=None,
        blockers=[],
        agent_contract_id=None,
        agent_version_id=None,
        release_change_request_id=None,
        requested_by_user_id=user_id,
        owner_user_id=user_id,
        reviewer_user_id=None,
        idempotency_key="service-test",
        correlation_id=uuid4(),
        last_error_code=None,
        created_at=now,
        analyzed_at=None,
        updated_at=now,
    )
    repository = Repository(record)
    registry = Registry()
    releases = Releases()
    service = GenesisFactoryService(
        repository,  # type: ignore[arg-type]
        Analyzer(),
        FactoryDependencyResolver(Catalog()),  # type: ignore[arg-type]
        registry,  # type: ignore[arg-type]
        releases,  # type: ignore[arg-type]
        limits=ExecutionLimits(),
    )

    result = service.analyze(
        record.factory_request_id,
        _actor(workspace_id, organization_id, user_id),
        correlation_id=uuid4(),
        agent_key="GENERIC_DAILY_REVIEW",
        name="Generic Daily Review",
    )

    assert result.status == FactoryStatus.DRAFT
    assert result.release_change_request_id == releases.change_request_id
    assert registry.contract.model_policy["execution_engine"] == "PYDANTICAI"
    assert {test.category for test in releases.tests} == {
        "POSITIVE",
        "NEGATIVE",
        "REGRESSION",
        "SECURITY",
        "RECOVERY",
    }
    assert all(test.expected_assertions["status"] != "EVIDENCE_REQUIRED" for test in releases.tests)


def test_factory_request_create_model_requires_idempotency_key() -> None:
    payload = FactoryRequestCreate(
        workspace_id=uuid4(),
        requirement="Create a persistent and governed Factory request.",
        idempotency_key="request-1",
    )

    assert payload.idempotency_key == "request-1"
