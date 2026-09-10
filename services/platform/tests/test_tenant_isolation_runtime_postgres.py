import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentContract, AgentRegistryRepository, LocalBootstrapRequest
from alos.config import Settings, get_settings
from alos.genesis.factory.persistence import FactoryRepository, FactoryRequestCreate
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.model_gateway import (
    FakeModelGateway,
    GuardedModelGateway,
    ModelResponse,
    ModelUsage,
    RetryingModelGateway,
    UsageBudget,
)
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.release.governance import ReleaseGovernanceError, ReleaseGovernanceRepository
from alos.runtime.service import (
    AgentRunRequest,
    AgentRuntime,
    AgentRuntimeBlocked,
    AgentRuntimeRepository,
)
from alos.security.tokens import ActorContext

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def _actor(context: object, tenant_id: object) -> ActorContext:
    now = datetime.now(UTC)
    return ActorContext(
        user_id=context.user_id,
        organization_id=context.organization_id,
        roles=[HumanRole.IT_LEAD],
        division_codes=[DivisionCode.IT],
        workspace_ids=[context.workspace_id],
        tenant_ids=[tenant_id],
        data_scope=DataScope.DIVISION,
        permissions=[],
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_runtime_requires_actor_claim_and_factory_tenant_lineage() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_tenant_runtime_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, root / "infra" / "database")
        registry = AgentRegistryRepository(temporary_url)
        context = registry.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        tenant_a, tenant_b = uuid4(), uuid4()
        actor_a = _actor(context, tenant_a)
        draft = registry.create_draft(
            AgentContract(
                agent_key="TENANT_MODEL_AGENT",
                name="Tenant Model Agent",
                workspace_id=context.workspace_id,
                purpose="Process one tenant-scoped model-only fixture.",
                risk_level="LOW",
                owner_user_id=context.user_id,
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "required": ["summary"],
                    "properties": {"summary": {"type": "string"}},
                },
                model_policy={"provider": "gemini", "max_output_tokens": 256},
                tool_keys=[],
                permission_keys=[],
                evidence_requirements=["tenant run fixture"],
                forbidden_actions=["No tool or cross-tenant access."],
                kpis=[],
                approval_required=True,
                timeout_seconds=30,
                prompt_template="Return only a tenant-scoped fixture summary.",
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            reason="tenant runtime fixture",
        )
        factory = FactoryRepository(temporary_url).create(
            FactoryRequestCreate(
                workspace_id=context.workspace_id,
                tenant_id=tenant_a,
                requirement="Process a tenant-scoped fixture without using business tools.",
                idempotency_key="tenant-runtime-fixture",
            ),
            actor_a,
            correlation_id=uuid4(),
        )
        release_repository = ReleaseGovernanceRepository(temporary_url)
        release = release_repository.create_release_request(
            "TENANT_MODEL_AGENT",
            context.workspace_id,
            "Release a model-only Agent bound to the authenticated tenant scope.",
            organization_id=context.organization_id,
            maker_user_id=context.user_id,
            tenant_id=tenant_a,
            correlation_id=uuid4(),
        )
        with psycopg.connect(temporary_url) as connection:
            connection.execute(
                (
                    "UPDATE agents.versions SET lifecycle_status = 'ACTIVE' "
                    "WHERE agent_version_id = %s"
                ),
                (draft.agent_version_id,),
            )
            connection.execute(
                """
                UPDATE agents.registry SET active_version_id = %s
                WHERE agent_contract_id = %s
                """,
                (draft.agent_version_id, draft.agent_contract_id),
            )
            connection.execute(
                """
                UPDATE genesis.factory_requests
                SET agent_contract_id = %s, agent_version_id = %s
                WHERE factory_request_id = %s
                """,
                (draft.agent_contract_id, draft.agent_version_id, factory.factory_request_id),
            )
            connection.commit()
        settings = Settings(
            _env_file=None,
            environment="test",
            database_url=temporary_url,
            auth_signing_secret="a" * 32,
            llm_provider="gemini",
            llm_api_key="test-only-key",
            llm_model="gemini-3.7-flash",
            llm_max_output_tokens=256,
            llm_daily_request_limit=10,
            llm_daily_output_token_limit=3_000,
            llm_daily_cost_cap_usd=Decimal("1.00"),
        )
        gateway = GuardedModelGateway(
            RetryingModelGateway(
                FakeModelGateway(
                    [
                        ModelResponse(
                            provider="gemini",
                            model="gemini-3.7-flash",
                            output_text='{"summary":"tenant A fixture"}',
                            usage=ModelUsage(input_tokens=5, output_tokens=5),
                            latency_milliseconds=1,
                            estimated_cost_usd=Decimal("0"),
                        )
                    ]
                ),
                max_retries=0,
            ),
            settings,
            UsageBudget(request_limit=2, output_token_limit=512),
        )
        runtime = AgentRuntime(AgentRuntimeRepository(temporary_url, settings), gateway, settings)
        result = runtime.execute(
            "TENANT_MODEL_AGENT",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                tenant_id=tenant_a,
                input={"fixture": "tenant A"},
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            actor=actor_a,
            allow_draft=False,
        )
        assert result.status == "SUCCEEDED"
        with pytest.raises(ReleaseGovernanceError, match="not found"):
            release_repository.get_release_request_detail(
                release.change_request_id,
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                tenant_ids=(tenant_b,),
            )
        with pytest.raises(AgentRuntimeBlocked, match="tenant"):
            runtime.execute(
                "TENANT_MODEL_AGENT",
                AgentRunRequest(
                    workspace_id=context.workspace_id,
                    tenant_id=tenant_b,
                    input={"fixture": "cross tenant"},
                ),
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                actor=actor_a,
                allow_draft=False,
            )
        with psycopg.connect(temporary_url) as connection:
            stored = connection.execute(
                "SELECT tenant_id, status FROM runtime.agent_runs WHERE agent_run_id = %s",
                (result.agent_run_id,),
            ).fetchone()
            assert stored == (tenant_a, "SUCCEEDED")
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
