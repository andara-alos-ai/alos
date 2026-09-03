import os
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from alos.agents.registry import AgentContract, AgentRegistryRepository, LocalBootstrapRequest
from alos.config import Settings, get_settings
from alos.model_gateway import (
    FakeModelGateway,
    GuardedModelGateway,
    ModelResponse,
    ModelUsage,
    RetryingModelGateway,
    UsageBudget,
)
from alos.permissions.registry import (
    PermissionConflictError,
    PermissionPolicyRequest,
    PermissionRegistryRepository,
)
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.runtime.service import AgentRunRequest, AgentRuntime, AgentRuntimeRepository
from alos.tools.registry import ToolConflictError, ToolDefinitionRequest, ToolRegistryRepository

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        auth_signing_secret="a" * 32,
        llm_provider="gemini",
        llm_api_key="test-only-key",
        llm_model="gemini-3.7-flash",
        llm_max_output_tokens=256,
        llm_daily_request_limit=10,
        llm_daily_output_token_limit=3_000,
        llm_daily_cost_cap_usd=Decimal("1.00"),
    )


def _contract(workspace_id: UUID, owner_user_id: UUID) -> AgentContract:
    return AgentContract(
        agent_key="POLICY_RUNTIME",
        name="Policy Runtime Fixture",
        workspace_id=workspace_id,
        purpose="Return a read-only fixture after an approved permission policy exists.",
        risk_level="LOW",
        owner_user_id=owner_user_id,
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        model_policy={"provider": "gemini", "max_output_tokens": 256},
        tool_keys=[],
        permission_keys=["SOURCE_READ_INTERNAL"],
        evidence_requirements=[],
        forbidden_actions=["Do not write or change production."],
        kpis=[{"name": "safe_result", "target": 1}],
        approval_required=True,
        timeout_seconds=120,
        prompt_template="Return a JSON summary only.",
    )


def _add_approver(
    database_url: str, organization_id: UUID, workspace_id: UUID
) -> UUID:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            INSERT INTO identity.users (organization_id, email, display_name)
            VALUES (%s, 'independent@alos.test', 'Independent Approver')
            RETURNING user_id
            """,
            (organization_id,),
        ).fetchone()
        assert row is not None
        user_id = UUID(str(row[0]))
        connection.execute(
            """
            INSERT INTO workspace.memberships (workspace_id, user_id, access_level)
            VALUES (%s, %s, 'OWNER')
            """,
            (workspace_id, user_id),
        )
        connection.commit()
    return user_id


def _runtime(database_url: str, settings: Settings) -> AgentRuntime:
    response = ModelResponse(
        provider="gemini",
        model="gemini-3.7-flash",
        output_text='{"summary":"approved policy fixture"}',
        usage=ModelUsage(input_tokens=10, output_tokens=10),
        latency_milliseconds=1,
        estimated_cost_usd=Decimal("0"),
    )
    return AgentRuntime(
        AgentRuntimeRepository(database_url, settings),
        GuardedModelGateway(
            RetryingModelGateway(FakeModelGateway([response]), max_retries=0),
            settings,
            UsageBudget(request_limit=1, output_token_limit=256),
        ),
        settings,
    )


def test_tool_and_permission_maker_approval_are_independent_and_runtime_enforced() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_h5_tool_policy_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        settings = _settings(temporary_url)
        agents = AgentRegistryRepository(temporary_url)
        context = agents.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        approver_user_id = _add_approver(
            temporary_url, context.organization_id, context.workspace_id
        )
        tools = ToolRegistryRepository(temporary_url)
        tool = tools.create_draft(
            ToolDefinitionRequest(
                tool_key="SOURCE_REGISTRY_SEARCH",
                name="Source Registry Search",
                manifest={
                    "access_mode": "READ_ONLY",
                    "runtime_handler": "SOURCE_REGISTRY_SEARCH",
                },
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        with pytest.raises(ToolConflictError, match="maker cannot approve"):
            tools.approve(
                tool.tool_key,
                organization_id=context.organization_id,
                approver_user_id=context.user_id,
                correlation_id=uuid4(),
            )
        assert tools.approve(
            tool.tool_key,
            organization_id=context.organization_id,
            approver_user_id=approver_user_id,
            correlation_id=uuid4(),
        ).lifecycle_status == "APPROVED"

        created = agents.create_draft(
            _contract(context.workspace_id, context.user_id),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            reason="H5 permission registry fixture",
        )
        assert _runtime(temporary_url, settings).execute(
            "POLICY_RUNTIME",
            AgentRunRequest(workspace_id=context.workspace_id),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        ).status == "BLOCKED"

        permissions = PermissionRegistryRepository(temporary_url)
        policy = permissions.create_draft(
            PermissionPolicyRequest(
                workspace_id=context.workspace_id,
                agent_key="POLICY_RUNTIME",
                semantic_version=created.semantic_version,
                permission_key="SOURCE_READ_INTERNAL",
                effect="ALLOW",
                resource_scope={"access_mode": "READ_ONLY", "classification": "INTERNAL"},
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        with pytest.raises(PermissionConflictError, match="maker cannot approve"):
            permissions.approve(
                policy.permission_policy_id,
                organization_id=context.organization_id,
                approver_user_id=context.user_id,
                correlation_id=uuid4(),
            )
        assert permissions.approve(
            policy.permission_policy_id,
            organization_id=context.organization_id,
            approver_user_id=approver_user_id,
            correlation_id=uuid4(),
        ).lifecycle_status == "APPROVED"
        assert _runtime(temporary_url, settings).execute(
            "POLICY_RUNTIME",
            AgentRunRequest(workspace_id=context.workspace_id),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        ).status == "SUCCEEDED"
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
