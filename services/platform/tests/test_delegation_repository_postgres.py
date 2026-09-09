import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentContract, AgentRegistryRepository, LocalBootstrapRequest
from alos.genesis.governed_foundations import Scope
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.runtime.delegation import DelegationBlocked, DelegationRepository, DelegationStatus

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def _contract(workspace_id, owner_user_id, key):
    return AgentContract(
        agent_key=key,
        name=key.replace("_", " ").title(),
        workspace_id=workspace_id,
        purpose="Execute one bounded delegated test responsibility.",
        risk_level="LOW",
        owner_user_id=owner_user_id,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        model_policy={"execution_engine": "PYDANTICAI"},
        tool_keys=[],
        permission_keys=[],
        evidence_requirements=["test evidence"],
        forbidden_actions=["No scope widening."],
        kpis=[],
        approval_required=True,
        timeout_seconds=30,
        prompt_template="Perform only the delegated bounded responsibility.",
    )


def test_delegation_uses_persistent_run_scope_and_lineage() -> None:
    from alos.config import get_settings

    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_delegation_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, root / "infra" / "database")
        registry = AgentRegistryRepository(temporary_url)
        context = registry.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        parent = registry.create_draft(
            _contract(context.workspace_id, context.user_id, "PARENT_AGENT"),
            context.organization_id,
            context.user_id,
            uuid4(),
            "delegation fixture",
        )
        child = registry.create_draft(
            _contract(context.workspace_id, context.user_id, "CHILD_AGENT"),
            context.organization_id,
            context.user_id,
            uuid4(),
            "delegation fixture",
        )
        tenant_a, tenant_b = uuid4(), uuid4()
        with psycopg.connect(temporary_url) as connection:
            connection.execute(
                """
                UPDATE agents.versions SET lifecycle_status = 'ACTIVE'
                WHERE agent_version_id = ANY(%s)
                """,
                ([parent.agent_version_id, child.agent_version_id],),
            )
            parent_run = connection.execute(
                """
                INSERT INTO runtime.agent_runs (
                    organization_id, workspace_id, tenant_id, agent_version_id,
                    requested_by_user_id, correlation_id, status, execution_mode, classification
                ) VALUES (%s, %s, %s, %s, %s, %s, 'RUNNING', 'TEST', 'INTERNAL')
                RETURNING agent_run_id
                """,
                (
                    context.organization_id,
                    context.workspace_id,
                    tenant_a,
                    parent.agent_version_id,
                    context.user_id,
                    uuid4(),
                ),
            ).fetchone()
            connection.commit()
        assert parent_run is not None
        scope = Scope(
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            tenant_id=tenant_a,
        )
        repository = DelegationRepository(temporary_url, max_depth=2, max_subagents=2)
        delegation = repository.request(
            parent_run[0],
            child.agent_version_id,
            scope,
            remaining_cost_budget=Decimal("1.00"),
        )
        assert delegation.status == DelegationStatus.REQUESTED
        assert repository.get(delegation.delegation_id).correlation_id == delegation.correlation_id

        with pytest.raises(DelegationBlocked, match="circular"):
            repository.request(
                parent_run[0],
                parent.agent_version_id,
                scope,
                remaining_cost_budget=Decimal("1.00"),
            )
        with pytest.raises(DelegationBlocked, match="scope"):
            repository.request(
                parent_run[0],
                child.agent_version_id,
                scope.model_copy(update={"tenant_id": tenant_b}),
                remaining_cost_budget=Decimal("1.00"),
            )
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
