"""Application orchestration for the persistent GENESIS Factory."""

from __future__ import annotations

from contextlib import suppress
from hashlib import sha256
from typing import Protocol, cast
from uuid import UUID

from alos.agents.registry import AgentRegistryRepository
from alos.authorization import require_agent_request
from alos.genesis.factory.models import RequirementUnderstanding
from alos.genesis.factory.persistence import (
    FactoryRepository,
    FactoryRequestCreate,
    FactoryRequestPage,
    FactoryRequestRecord,
    FactoryStatus,
)
from alos.genesis.factory.pipeline import (
    AgentContractFactory,
    FactoryDependencyResolver,
    GeneratedTest,
)
from alos.genesis.factory.resolver import ImplementationTypeResolver
from alos.release.governance import (
    ReleaseGovernanceRepository,
    TestCaseRequest,
    TestCategory,
)
from alos.runtime.agentic import ExecutionContext, ExecutionLimits, ExecutionMode
from alos.security.tokens import ActorContext


class FactoryAnalysisError(RuntimeError):
    """The Factory pipeline stopped after persisting a safe blocker."""


class SemanticRequirementAnalyzer(Protocol):
    def analyze(
        self,
        requirement: str,
        *,
        context: ExecutionContext,
        limits: ExecutionLimits,
    ) -> RequirementUnderstanding: ...


class GenesisFactoryService:
    """Coordinate analysis, resolution, persistence, Registry, and Governance."""

    def __init__(
        self,
        repository: FactoryRepository,
        analyzer: SemanticRequirementAnalyzer,
        dependency_resolver: FactoryDependencyResolver,
        agent_registry: AgentRegistryRepository,
        releases: ReleaseGovernanceRepository,
        *,
        limits: ExecutionLimits,
    ) -> None:
        self._repository = repository
        self._analyzer = analyzer
        self._implementation_resolver = ImplementationTypeResolver()
        self._dependency_resolver = dependency_resolver
        self._contract_factory = AgentContractFactory()
        self._agent_registry = agent_registry
        self._releases = releases
        self._limits = limits

    def create(
        self,
        request: FactoryRequestCreate,
        actor: ActorContext,
        *,
        correlation_id: UUID,
    ) -> FactoryRequestRecord:
        require_agent_request(actor, None)
        return self._repository.create(request, actor, correlation_id=correlation_id)

    def get(self, request_id: UUID, actor: ActorContext) -> FactoryRequestRecord:
        return self._repository.get(request_id, actor)

    def list_requests(
        self,
        actor: ActorContext,
        *,
        workspace_id: UUID | None,
        status: FactoryStatus | None,
        limit: int,
        offset: int,
    ) -> FactoryRequestPage:
        return self._repository.list_requests(
            actor,
            workspace_id=workspace_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def analyze(
        self,
        request_id: UUID,
        actor: ActorContext,
        *,
        correlation_id: UUID,
        agent_key: str | None = None,
        name: str | None = None,
    ) -> FactoryRequestRecord:
        require_agent_request(actor, None)
        request = self._repository.begin_analysis(
            request_id, actor, correlation_id=correlation_id
        )
        try:
            understanding = self._analyzer.analyze(
                request.requirement,
                context=self._execution_context(request, actor, correlation_id),
                limits=self._limits,
            )
            decision = self._implementation_resolver.resolve(understanding)
            resolution = self._dependency_resolver.resolve(decision.required_capabilities)
            digest = sha256(request.requirement.encode("utf-8")).hexdigest().upper()
            proposal = self._contract_factory.create(
                understanding,
                decision,
                resolution,
                agent_key=agent_key or f"GENESIS_{digest[:12]}",
                name=name or f"Genesis Proposal {digest[:8]}",
                workspace_id=request.workspace_id,
                owner_user_id=request.owner_user_id or actor.user_id,
            )
            persisted = self._repository.complete_analysis(
                request_id,
                actor,
                understanding=understanding,
                decision=decision,
                proposal=proposal,
                agent_contract_id=None,
                agent_version_id=None,
                correlation_id=correlation_id,
            )
            if proposal.agent_contract is None or persisted.status != FactoryStatus.DRAFT:
                return persisted
            draft = self._agent_registry.create_draft(
                proposal.agent_contract,
                organization_id=actor.organization_id,
                actor_user_id=actor.user_id,
                correlation_id=correlation_id,
                reason="GENESIS Factory created a governed Agent Contract DRAFT",
            )
            release = self._releases.create_release_request(
                draft.agent_key,
                request.workspace_id,
                request.requirement,
                organization_id=actor.organization_id,
                maker_user_id=actor.user_id,
                requested_by_user_id=request.requested_by_user_id,
                correlation_id=correlation_id,
            )
            self._register_governance_tests(
                release.change_request_id,
                proposal.tests,
                actor,
                correlation_id,
            )
            return self._repository.link_governance(
                request_id,
                actor,
                agent_contract_id=draft.agent_contract_id,
                agent_version_id=draft.agent_version_id,
                release_change_request_id=release.change_request_id,
                correlation_id=correlation_id,
            )
        except Exception as error:
            with suppress(Exception):
                self._repository.fail_analysis(
                    request_id,
                    actor,
                    error_code=type(error).__name__.upper()[:120],
                    reason=str(error) or "Factory pipeline failed safely",
                    correlation_id=correlation_id,
                )
            raise FactoryAnalysisError("Factory analysis was blocked; inspect blockers") from error

    @staticmethod
    def _execution_context(
        request: FactoryRequestRecord,
        actor: ActorContext,
        correlation_id: UUID,
    ) -> ExecutionContext:
        actor_role = actor.roles[0].value if actor.roles else "UNKNOWN"
        return ExecutionContext(
            organization_id=actor.organization_id,
            workspace_id=request.workspace_id,
            division_id=request.division_id,
            project_id=request.project_id,
            tenant_id=request.tenant_id,
            actor_user_id=actor.user_id,
            actor_role=actor_role,
            agent_id=request.factory_request_id,
            agent_version_id=request.factory_request_id,
            run_id=request.factory_request_id,
            correlation_id=correlation_id,
            execution_mode=ExecutionMode.TEST,
            classification="INTERNAL",
        )

    def _register_governance_tests(
        self,
        change_request_id: UUID,
        tests: tuple[GeneratedTest, ...],
        actor: ActorContext,
        correlation_id: UUID,
    ) -> None:
        supported = {"POSITIVE", "NEGATIVE", "REGRESSION", "SECURITY", "RECOVERY"}
        for sequence, test in enumerate(
            (item for item in tests if item.category in supported), start=1
        ):
            category = cast(TestCategory, test.category)
            expected = "BLOCKED" if category in {"NEGATIVE", "SECURITY"} else "SUCCEEDED"
            self._releases.register_test_case(
                change_request_id,
                TestCaseRequest(
                    test_key=f"FACTORY_{category}_{sequence}",
                    category=category,
                    input_fixture={
                        "input": {"factory_test_objective": test.objective},
                        "requested_tool_keys": [],
                    },
                    expected_assertions={"status": expected},
                ),
                actor_user_id=actor.user_id,
                correlation_id=correlation_id,
            )
