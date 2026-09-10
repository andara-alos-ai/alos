import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentContract, AgentRegistryRepository, LocalBootstrapRequest
from alos.config import Settings, get_settings
from alos.identity import DataScope, DivisionCode, HumanRole
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.runtime.service import AgentRuntimeRepository
from alos.security.tokens import ActorContext

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def test_persistent_cancel_request_is_queryable_across_repository_instances() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_agent_cancel_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, root / "infra" / "database")
        registry = AgentRegistryRepository(temporary_url)
        context = registry.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        draft = registry.create_draft(
            AgentContract(
                agent_key="CANCEL_MODEL_AGENT",
                name="Cancel Model Agent",
                workspace_id=context.workspace_id,
                purpose="Validate durable cancellation state.",
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
                evidence_requirements=["cancellation fixture"],
                forbidden_actions=["No tool or cross-tenant access."],
                kpis=[],
                approval_required=True,
                timeout_seconds=30,
                prompt_template="Return a cancellation fixture summary.",
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            reason="cancellation fixture",
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
                "UPDATE agents.registry SET active_version_id = %s WHERE agent_contract_id = %s",
                (draft.agent_version_id, draft.agent_contract_id),
            )
            run = connection.execute(
                """
                INSERT INTO runtime.agent_runs (
                    organization_id, workspace_id, agent_version_id, requested_by_user_id,
                    correlation_id, status
                ) VALUES (%s, %s, %s, %s, %s, 'RUNNING')
                RETURNING agent_run_id
                """,
                (
                    context.organization_id,
                    context.workspace_id,
                    draft.agent_version_id,
                    context.user_id,
                    uuid4(),
                ),
            ).fetchone()
            assert run is not None
            run_id = run[0]
            connection.commit()
        now = datetime.now(UTC)
        actor = ActorContext(
            user_id=context.user_id,
            organization_id=context.organization_id,
            roles=[HumanRole.IT_LEAD],
            division_codes=[DivisionCode.IT],
            workspace_ids=[context.workspace_id],
            tenant_ids=[],
            data_scope=DataScope.DIVISION,
            permissions=[],
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        settings = Settings(
            _env_file=None,
            environment="test",
            database_url=temporary_url,
            auth_signing_secret="a" * 32,
        )
        repository = AgentRuntimeRepository(temporary_url, settings)
        summary = repository.cancel_run(run_id, actor, correlation_id=uuid4())
        assert summary.status == "CANCEL_REQUESTED"
        assert repository.is_cancel_requested(run_id)
        reloaded = AgentRuntimeRepository(temporary_url, settings)
        assert reloaded.is_cancel_requested(run_id)
        with psycopg.connect(temporary_url) as connection:
            stored = connection.execute(
                (
                    "SELECT status, cancel_requested_at IS NOT NULL "
                    "FROM runtime.agent_runs WHERE agent_run_id = %s"
                ),
                (run_id,),
            ).fetchone()
            assert stored == ("CANCEL_REQUESTED", True)
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
