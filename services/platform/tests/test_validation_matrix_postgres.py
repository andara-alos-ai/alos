import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from alos.agents.registry import AgentContract, AgentRegistryRepository, LocalBootstrapRequest
from alos.config import Settings, get_settings
from alos.identity import DivisionCode
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
        llm_daily_request_limit=50,
        llm_daily_output_token_limit=6_000,
        llm_daily_cost_cap_usd=Decimal("1.00"),
    )


def _contract(agent_key: str, workspace_id: UUID, owner_user_id: UUID) -> AgentContract:
    output_schema_by_agent = {
        "DAILY_BRIEF": {
            "type": "object",
            "required": ["summary", "highlights", "citations"],
            "properties": {
                "summary": {"type": "string"},
                "highlights": {"type": "array"},
                "citations": {"type": "array"},
            },
        },
        "EVIDENCE_CHECKER": {
            "type": "object",
            "required": ["assessment", "gaps", "citations"],
            "properties": {
                "assessment": {"type": "string"},
                "gaps": {"type": "array"},
                "citations": {"type": "array"},
            },
        },
        "PERMIT_OVERDUE_MONITOR": {
            "type": "object",
            "required": ["summary", "alerts", "citations"],
            "properties": {
                "summary": {"type": "string"},
                "alerts": {"type": "array"},
                "citations": {"type": "array"},
            },
        },
    }
    return AgentContract(
        agent_key=agent_key,
        name=agent_key.replace("_", " ").title(),
        workspace_id=workspace_id,
        purpose="Read verified internal evidence only and never perform a side effect.",
        risk_level="LOW",
        owner_user_id=owner_user_id,
        input_schema={
            "type": "object",
            "required": ["division_code"],
            "properties": {"division_code": {"type": "string"}},
        },
        output_schema=output_schema_by_agent[agent_key],
        model_policy={"provider": "gemini", "max_output_tokens": 256},
        tool_keys=["SOURCE_REGISTRY_SEARCH"],
        permission_keys=["SOURCE_READ_INTERNAL"],
        evidence_requirements=["verified evidence citation"],
        forbidden_actions=[
            "Do not write, contact third parties, spend funds, or change production."
        ],
        kpis=[{"name": "citation_coverage", "target": 1}],
        approval_required=True,
        timeout_seconds=120,
        prompt_template="Use only retrieved evidence. Return JSON and take no actions.",
    )


def _response(citation_key: str) -> ModelResponse:
    output = {
        "summary": "Synthetic division validation summary.",
        "highlights": [],
        "assessment": "SUPPORTED by the retrieved synthetic evidence.",
        "gaps": [],
        "alerts": [],
        "citations": [citation_key],
    }
    return ModelResponse(
        provider="gemini",
        model="gemini-3.7-flash",
        output_text=json.dumps(output),
        usage=ModelUsage(input_tokens=12, output_tokens=20),
        latency_milliseconds=1,
        estimated_cost_usd=Decimal("0"),
    )


def test_three_validation_agents_run_across_six_division_contexts() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_h5_matrix_{uuid4().hex}"
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
        citation_by_division: dict[DivisionCode, str] = {}
        for division in DivisionCode:
            source_key = f"{division.value}_VALIDATION"
            sources.register(
                SourceRegistrationRequest(
                    workspace_id=context.workspace_id,
                    source_key=source_key,
                    name=f"Synthetic {division.value} validation source",
                    version_label="v1",
                    locator=f"synthetic://validation/{division.value.lower()}",
                    content=(
                        f"division_code={division.value}\n"
                        "status=verified synthetic validation evidence"
                    ),
                ),
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                correlation_id=uuid4(),
            )
            sources.verify(
                context.workspace_id,
                source_key,
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                correlation_id=uuid4(),
                reason="Verify synthetic H5 division validation evidence.",
            )
            citation_by_division[division] = sources.search_evidence(
                context.workspace_id,
                division.value,
                organization_id=context.organization_id,
            )[0].citation_key

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

        for agent_key in ("DAILY_BRIEF", "EVIDENCE_CHECKER", "PERMIT_OVERDUE_MONITOR"):
            created = registry.create_draft(
                _contract(agent_key, context.workspace_id, context.user_id),
                organization_id=context.organization_id,
                actor_user_id=context.user_id,
                correlation_id=uuid4(),
                reason="H5 validation matrix Agent Contract fixture",
            )
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

        outcomes = [
            _response(citation_by_division[division])
            for agent_key in ("DAILY_BRIEF", "EVIDENCE_CHECKER", "PERMIT_OVERDUE_MONITOR")
            for division in DivisionCode
        ]
        runtime = AgentRuntime(
            AgentRuntimeRepository(temporary_url, settings),
            GuardedModelGateway(
                RetryingModelGateway(FakeModelGateway(outcomes), max_retries=0),
                settings,
                UsageBudget(request_limit=18, output_token_limit=5_000),
            ),
            settings,
        )
        results = []
        for agent_key in ("DAILY_BRIEF", "EVIDENCE_CHECKER", "PERMIT_OVERDUE_MONITOR"):
            for division in DivisionCode:
                results.append(
                    runtime.execute(
                        agent_key,
                        AgentRunRequest(
                            workspace_id=context.workspace_id,
                            input={"division_code": division.value},
                            requested_tool_keys=["SOURCE_REGISTRY_SEARCH"],
                        ),
                        organization_id=context.organization_id,
                        actor_user_id=context.user_id,
                    )
                )
        assert len(results) == 18
        assert all(result.status == "SUCCEEDED" for result in results)
        assert all(result.tool_decisions[0].decision == "ALLOWED" for result in results)
        run_summaries = AgentRuntimeRepository(temporary_url, settings).list_runs(
            context.workspace_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            limit=50,
        )
        assert len(run_summaries) == 18
        assert AgentRuntimeRepository(temporary_url, settings).usage_summary(
            context.workspace_id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
        ).request_count == 18
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
