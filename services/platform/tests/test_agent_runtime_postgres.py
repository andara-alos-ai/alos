import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

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
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.runtime.service import (
    AgentRunRequest,
    AgentRuntime,
    AgentRuntimeRepository,
    WorkspaceBudgetRequest,
)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL quality tests",
    ),
]


def _settings(database_url: str, *, environment: str = "test") -> Settings:
    return Settings(
        _env_file=None,
        environment=environment,
        database_url=database_url,
        auth_signing_secret="a" * 32,
        llm_provider="openai",
        llm_api_key="test-only-key",
        llm_model="gpt-5.6-luna",
        llm_model_light="gpt-5.6-luna",
        llm_model_standard="gpt-5.6-terra",
        llm_model_critical="gpt-5.6-sol",
        llm_max_output_tokens=300,
        llm_daily_request_limit=1,
        llm_daily_output_token_limit=1_000,
        llm_daily_cost_cap_usd=Decimal("1.00"),
    )


def _contract(workspace_id: object, owner_user_id: object) -> AgentContract:
    return AgentContract(
        agent_key="FIXTURE_RUNTIME",
        name="Fixture Runtime",
        workspace_id=workspace_id,
        purpose="Return a cited synthetic fixture result without changing any data.",
        risk_level="LOW",
        owner_user_id=owner_user_id,
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["summary", "citations"],
            "properties": {
                "summary": {"type": "string"},
                "citations": {"type": "array"},
            },
        },
        model_policy={"provider": "openai", "max_output_tokens": 300},
        tool_keys=["FIXTURE_SOURCE_READ"],
        permission_keys=[],
        evidence_requirements=["fixture reference"],
        forbidden_actions=["No write, external action, or production change."],
        kpis=[{"name": "fixture_response", "target": 1}],
        approval_required=True,
        timeout_seconds=120,
        prompt_template="Return a short cited response using only the read-only fixture context.",
    )


def _response() -> ModelResponse:
    return ModelResponse(
        provider="openai",
        model="gpt-5.6-luna",
        output_text='{"summary":"Fixture result","citations":["FIXTURE-PROPERTY-001"]}',
        usage=ModelUsage(input_tokens=12, output_tokens=20),
        latency_milliseconds=10,
        estimated_cost_usd=Decimal("0.000027"),
    )


def test_runtime_persists_usage_and_blocks_tools_and_budget() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_h3_runtime_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        settings = _settings(temporary_url, environment="staging")
        registry = AgentRegistryRepository(temporary_url)
        context = registry.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        # Staging requires an explicit persistent workspace cost limit before any
        # run (auto-seeding is local/test only). A director sets a generous fixture
        # limit here; the hard-stop behaviour is exercised by resetting it to 0 below.
        AgentRuntimeRepository(temporary_url, settings).set_budget_limit(
            context.workspace_id,
            WorkspaceBudgetRequest(
                daily_request_limit=50,
                daily_output_token_limit=10_000,
                daily_cost_cap_usd=Decimal("1.00"),
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        with psycopg.connect(temporary_url) as connection:
            connection.execute(
                """
                INSERT INTO agents.tool_definitions (
                    organization_id, tool_key, name, risk_level, manifest, lifecycle_status
                ) VALUES (
                    %s, 'FIXTURE_SOURCE_READ', 'Read-only fixture source', 'LOW', %s, 'APPROVED'
                )
                """,
                (
                    context.organization_id,
                    Jsonb(
                        {
                            "access_mode": "READ_ONLY",
                            "runtime_handler": "FIXTURE_SOURCE_READ",
                        }
                    ),
                ),
            )
            connection.commit()
        registry.create_draft(
            _contract(context.workspace_id, context.user_id),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            reason="H3 Runtime fixture",
        )
        fake = FakeModelGateway([_response(), _response()])
        runtime = AgentRuntime(
            AgentRuntimeRepository(temporary_url, settings),
            GuardedModelGateway(
                RetryingModelGateway(fake, max_retries=1),
                settings,
                UsageBudget(request_limit=1, output_token_limit=300),
            ),
            settings,
        )

        missing_limit = runtime.execute(
            "FIXTURE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"query": "property opportunity"},
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert missing_limit.status == "BLOCKED"
        assert missing_limit.tool_decisions[0].tool_key == "BUDGET_POLICY"

        fixture_budget = AgentRuntimeRepository(temporary_url, settings).set_budget_limit(
            context.workspace_id,
            WorkspaceBudgetRequest(
                daily_request_limit=1,
                daily_output_token_limit=1_000,
                daily_cost_cap_usd=Decimal("1.00"),
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        assert fixture_budget.daily_cost_cap_usd == Decimal("1.00")

        result = runtime.execute(
            "FIXTURE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"query": "property opportunity"},
                requested_tool_keys=["FIXTURE_SOURCE_READ"],
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert result.status == "SUCCEEDED"
        assert result.output == {
            "summary": "Fixture result",
            "citations": ["FIXTURE-PROPERTY-001"],
        }
        assert result.tool_decisions[0].decision == "ALLOWED"

        blocked = runtime.execute(
            "FIXTURE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"query": "property opportunity"},
                requested_tool_keys=["UNAPPROVED_TOOL"],
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert blocked.status == "BLOCKED"
        assert blocked.tool_decisions[0].decision == "BLOCKED"

        request_budget_blocked = runtime.execute(
            "FIXTURE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"query": "property opportunity"},
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert request_budget_blocked.status == "BLOCKED"
        assert request_budget_blocked.tool_decisions[0].tool_key == "BUDGET_POLICY"

        updated_budget = AgentRuntimeRepository(temporary_url, settings).set_budget_limit(
            context.workspace_id,
            WorkspaceBudgetRequest(
                daily_request_limit=2,
                daily_output_token_limit=1_000,
                daily_cost_cap_usd=Decimal("1.00"),
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        assert updated_budget.daily_request_limit == 2
        runtime_after_budget = AgentRuntime(
            AgentRuntimeRepository(temporary_url, settings),
            GuardedModelGateway(
                RetryingModelGateway(fake, max_retries=1),
                settings,
                UsageBudget(request_limit=1, output_token_limit=300),
            ),
            settings,
        )
        assert (
            runtime_after_budget.execute(
                "FIXTURE_RUNTIME",
                AgentRunRequest(
                    workspace_id=context.workspace_id,
                    input={"query": "property opportunity"},
                ),
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
            ).status
            == "SUCCEEDED"
        )

        AgentRuntimeRepository(temporary_url, settings).set_budget_limit(
            context.workspace_id,
            WorkspaceBudgetRequest(
                daily_request_limit=3,
                daily_output_token_limit=1_000,
                daily_cost_cap_usd=Decimal("1.00"),
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        in_memory_budget_blocked = runtime_after_budget.execute(
            "FIXTURE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"query": "property opportunity"},
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert in_memory_budget_blocked.status == "BLOCKED"
        assert in_memory_budget_blocked.error_code == "REQUEST_LIMIT"
        assert in_memory_budget_blocked.tool_decisions[-1].tool_key == "BUDGET_POLICY"
        assert in_memory_budget_blocked.tool_decisions[-1].decision == "BLOCKED"

        AgentRuntimeRepository(temporary_url, settings).set_budget_limit(
            context.workspace_id,
            WorkspaceBudgetRequest(
                daily_request_limit=4,
                daily_output_token_limit=1_000,
                daily_cost_cap_usd=Decimal("0"),
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        cost_blocked = runtime_after_budget.execute(
            "FIXTURE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"query": "property opportunity"},
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert cost_blocked.status == "BLOCKED"
        assert cost_blocked.tool_decisions[0].tool_key == "BUDGET_POLICY"

        with psycopg.connect(temporary_url) as connection:
            ledger_count = connection.execute(
                "SELECT count(*) FROM observability.usage_ledger"
            ).fetchone()
            assert ledger_count == (2,)
            assert connection.execute(
                "SELECT decision FROM runtime.tool_calls WHERE decision = 'BLOCKED'"
            ).fetchone() == ("BLOCKED",)
            assert connection.execute(
                "SELECT action FROM audit.events WHERE action = 'AGENT_RUN_BLOCKED'"
            ).fetchone() == ("AGENT_RUN_BLOCKED",)
            assert connection.execute(
                "SELECT action FROM audit.events WHERE action = 'COST_LIMIT_UPDATED'"
            ).fetchone() == ("COST_LIMIT_UPDATED",)
            assert connection.execute(
                "SELECT decision FROM runtime.tool_calls WHERE tool_key = 'BUDGET_POLICY'"
            ).fetchone() == ("BLOCKED",)
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
