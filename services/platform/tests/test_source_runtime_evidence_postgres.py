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
from alos.runtime.service import AgentRunRequest, AgentRuntime, AgentRuntimeRepository
from alos.sources.registry import SourceRegistrationRequest, SourceRegistryRepository

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


def _contract(workspace_id: object, owner_user_id: object) -> AgentContract:
    return AgentContract(
        agent_key="EVIDENCE_RUNTIME",
        name="Evidence Runtime Fixture",
        workspace_id=workspace_id,
        purpose="Assess a claim from verified read-only evidence with citations.",
        risk_level="LOW",
        owner_user_id=owner_user_id,
        input_schema={
            "type": "object",
            "required": ["claim"],
            "properties": {"claim": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["assessment", "citations"],
            "properties": {
                "assessment": {"type": "string"},
                "citations": {"type": "array"},
            },
        },
        model_policy={"provider": "gemini", "max_output_tokens": 256},
        tool_keys=["SOURCE_REGISTRY_SEARCH"],
        permission_keys=["SOURCE_READ_INTERNAL"],
        evidence_requirements=["verified source citation"],
        forbidden_actions=["Do not write, contact third parties, or change production."],
        kpis=[{"name": "citation_coverage", "target": 1}],
        approval_required=True,
        timeout_seconds=120,
        prompt_template=(
            "Assess only the retrieved evidence. Return cited JSON and take no actions."
        ),
    )


def _response(citation_key: str) -> ModelResponse:
    return ModelResponse(
        provider="gemini",
        model="gemini-3.7-flash",
        output_text=(
            '{"assessment":"SUPPORTED by the verified synthetic report",'
            f'"citations":["{citation_key}"]}}'
        ),
        usage=ModelUsage(input_tokens=12, output_tokens=18),
        latency_milliseconds=10,
        estimated_cost_usd=Decimal("0"),
    )


def _runtime(
    database_url: str, settings: Settings, response: ModelResponse
) -> AgentRuntime:
    return AgentRuntime(
        AgentRuntimeRepository(database_url, settings),
        GuardedModelGateway(
            RetryingModelGateway(FakeModelGateway([response]), max_retries=0),
            settings,
            UsageBudget(request_limit=1, output_token_limit=256),
        ),
        settings,
    )


def test_verified_source_permission_and_citation_guardrails_are_persisted() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_h5_evidence_{uuid4().hex}"
    maintenance_url = base_url.rsplit("/", 1)[0] + "/postgres"
    temporary_url = base_url.rsplit("/", 1)[0] + f"/{database_name}"
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        repository_root = Path(__file__).resolve().parents[3]
        apply_migrations(temporary_url, repository_root / "infra" / "database")
        settings = _settings(temporary_url)
        registry = AgentRegistryRepository(temporary_url)
        context = registry.bootstrap_local_context(LocalBootstrapRequest(), uuid4())
        sources = SourceRegistryRepository(temporary_url)
        registered = sources.register(
            SourceRegistrationRequest(
                workspace_id=context.workspace_id,
                source_key="SALES_DAILY",
                name="Synthetic Sales Daily",
                version_label="v1",
                locator="synthetic://sales/daily-v1",
                content="Pipeline: Rp1.55B\nStatus: current approved synthetic value",
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
        )
        assert sources.search_evidence(
            context.workspace_id, "Pipeline", organization_id=context.organization_id
        ) == []
        verified = sources.verify(
            context.workspace_id,
            "SALES_DAILY",
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            reason="Synthetic fixture content checked for local H5 validation.",
        )
        assert verified.status == "VERIFIED"
        evidence = sources.search_evidence(
            context.workspace_id, "Pipeline", organization_id=context.organization_id
        )
        assert len(evidence) == registered.citation_count == 1
        citation_key = evidence[0].citation_key

        with psycopg.connect(temporary_url) as connection:
            connection.execute(
                """
                INSERT INTO agents.tool_definitions (
                    organization_id, tool_key, name, risk_level, manifest, lifecycle_status
                ) VALUES (
                    %s, 'SOURCE_REGISTRY_SEARCH', 'Source Registry Search', 'LOW', %s, 'APPROVED'
                )
                """,
                (
                    context.organization_id,
                    Jsonb(
                        {
                            "access_mode": "READ_ONLY",
                            "runtime_handler": "SOURCE_REGISTRY_SEARCH",
                        }
                    ),
                ),
            )
            connection.commit()
        created = registry.create_draft(
            _contract(context.workspace_id, context.user_id),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            correlation_id=uuid4(),
            reason="H5 source evidence runtime fixture",
        )

        blocked = _runtime(temporary_url, settings, _response(citation_key)).execute(
            "EVIDENCE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"claim": "Pipeline"},
                requested_tool_keys=["SOURCE_REGISTRY_SEARCH"],
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert blocked.status == "BLOCKED"
        assert blocked.tool_decisions[0].tool_key == "PERMISSION_POLICY"

        with psycopg.connect(temporary_url) as connection:
            connection.execute(
                """
                INSERT INTO governance.permission_policies (
                    organization_id, workspace_id, agent_version_id, permission_key, effect,
                    resource_scope, approval_required, lifecycle_status
                ) VALUES (%s, %s, %s, 'SOURCE_READ_INTERNAL', 'ALLOW', %s, true, 'APPROVED')
                """,
                (
                    context.organization_id,
                    context.workspace_id,
                    created.agent_version_id,
                    Jsonb({"classification": "INTERNAL", "access_mode": "READ_ONLY"}),
                ),
            )
            connection.commit()

        succeeded = _runtime(temporary_url, settings, _response(citation_key)).execute(
            "EVIDENCE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"claim": "Pipeline"},
                requested_tool_keys=["SOURCE_REGISTRY_SEARCH"],
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert succeeded.status == "SUCCEEDED"
        assert succeeded.tool_decisions[0].decision == "ALLOWED"

        invalid = _runtime(temporary_url, settings, _response("INVENTED-CITATION")).execute(
            "EVIDENCE_RUNTIME",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"claim": "Pipeline"},
                requested_tool_keys=["SOURCE_REGISTRY_SEARCH"],
            ),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert invalid.status == "FAILED"
        assert invalid.error_code == "OUTPUT_SCHEMA_INVALID"

        runtime_repository = AgentRuntimeRepository(temporary_url, settings)
        runs = runtime_repository.list_runs(
            context.workspace_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert [run.status for run in runs] == ["FAILED", "SUCCEEDED", "BLOCKED"]
        usage = runtime_repository.usage_summary(
            context.workspace_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        )
        assert usage.request_count == 2
        assert usage.output_tokens == 36
        with psycopg.connect(temporary_url) as connection:
            actions = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT action FROM audit.events
                    WHERE action IN (
                        'SOURCE_VERSION_REGISTERED', 'SOURCE_VERIFIED', 'AGENT_RUN_SUCCEEDED'
                    )
                    """
                ).fetchall()
            }
        assert actions == {"SOURCE_VERSION_REGISTERED", "SOURCE_VERIFIED", "AGENT_RUN_SUCCEEDED"}
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
