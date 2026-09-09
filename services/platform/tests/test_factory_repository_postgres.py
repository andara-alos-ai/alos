import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentRegistryRepository, LocalBootstrapRequest
from alos.genesis.factory.models import (
    ImplementationDecision,
    ImplementationType,
    RequirementUnderstanding,
    TriggerKind,
)
from alos.genesis.factory.persistence import (
    FactoryRepository,
    FactoryRequestConflictError,
    FactoryRequestCreate,
    FactoryRequestNotFoundError,
    FactoryStatus,
)
from alos.genesis.factory.pipeline import (
    DependencyStatus,
    FactoryProposal,
    FactoryResolution,
    GeneratedTest,
)
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.security.tokens import ActorContext

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def _actor(
    *, organization_id, user_id, workspace_id, tenant_ids=()
) -> ActorContext:
    now = datetime.now(UTC)
    return ActorContext(
        user_id=user_id,
        organization_id=organization_id,
        roles=[HumanRole.IT_LEAD],
        division_codes=[DivisionCode.IT],
        workspace_ids=[workspace_id],
        tenant_ids=list(tenant_ids),
        data_scope=DataScope.DIVISION,
        permissions=[],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_factory_request_survives_reload_and_enforces_tenant_scope() -> None:
    from alos.config import get_settings

    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_factory_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        context = AgentRegistryRepository(temporary_url).bootstrap_local_context(
            LocalBootstrapRequest(), uuid4()
        )
        tenant_a, tenant_b = uuid4(), uuid4()
        actor_a = _actor(
            organization_id=context.organization_id,
            user_id=context.user_id,
            workspace_id=context.workspace_id,
            tenant_ids=(tenant_a,),
        )
        repository = FactoryRepository(temporary_url)
        create = FactoryRequestCreate(
            workspace_id=context.workspace_id,
            tenant_id=tenant_a,
            requirement="Enforce an approval workflow for configured transaction thresholds.",
            idempotency_key="factory-persistence-1",
        )

        record = repository.create(create, actor_a, correlation_id=uuid4())
        duplicate = repository.create(create, actor_a, correlation_id=uuid4())
        assert duplicate.factory_request_id == record.factory_request_id
        with pytest.raises(FactoryRequestConflictError):
            repository.create(
                create.model_copy(update={"requirement": "A different valid requirement."}),
                actor_a,
                correlation_id=uuid4(),
            )

        repository.begin_analysis(record.factory_request_id, actor_a, correlation_id=uuid4())
        understanding = RequirementUnderstanding(
            objective="Enforce approval for configured transaction thresholds.",
            trigger_kind=TriggerKind.CONDITIONAL,
            required_capabilities=("approval.request",),
            required_data=("transaction amount", "configured threshold"),
            deterministic_constraints=("amount exceeds configured threshold",),
            material_actions=("request approval",),
        )
        decision = ImplementationDecision(
            implementation_type=ImplementationType.COMPOSITE,
            components=(ImplementationType.RULE, ImplementationType.WORKFLOW),
            reason="A deterministic rule and governed workflow satisfy the requirement.",
            required_capabilities=understanding.required_capabilities,
            required_data=understanding.required_data,
            risk="MEDIUM",
            human_gate_required=True,
        )
        resolution = FactoryResolution(
            capability_keys=(),
            tool_keys=(),
            permission_keys=(),
            readiness=DependencyStatus.AVAILABLE,
        )
        proposal = FactoryProposal(
            decision=decision,
            resolution=resolution,
            agent_contract=None,
            tests=(
                GeneratedTest(
                    category="SECURITY",
                    objective="Verify unauthorized approval is denied.",
                    expected_status="EVIDENCE_REQUIRED",
                ),
            ),
        )
        completed = repository.complete_analysis(
            record.factory_request_id,
            actor_a,
            understanding=understanding,
            decision=decision,
            proposal=proposal,
            agent_contract_id=None,
            agent_version_id=None,
            correlation_id=uuid4(),
        )
        assert completed.status == FactoryStatus.DRAFT
        assert completed.generated_tests[0].execution_status == "NOT_RUN"

        reloaded = FactoryRepository(temporary_url).get(record.factory_request_id, actor_a)
        assert reloaded.requirement_understanding == understanding
        assert reloaded.generated_tests[0].expected_status == "EVIDENCE_REQUIRED"
        listed = FactoryRepository(temporary_url).list_requests(actor_a)
        assert listed.items[0].factory_request_id == record.factory_request_id

        actor_b = actor_a.model_copy(update={"tenant_ids": [tenant_b]})
        with pytest.raises(FactoryRequestNotFoundError):
            repository.get(record.factory_request_id, actor_b)
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
