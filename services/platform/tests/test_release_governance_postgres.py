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
from alos.persistence.database import psycopg_url
from alos.persistence.migrations import apply_migrations
from alos.release.governance import (
    AgentTestRunner,
    LifecycleConflictError,
    ReleaseGovernanceError,
    ReleaseGovernanceRepository,
    ReviewRequest,
    RollbackRequest,
    SegregationOfDutiesError,
)
from alos.release.governance import (
    TestCaseRequest as ReleaseTestCaseRequest,
)
from alos.runtime.service import (
    AgentRunRequest,
    AgentRunResult,
    AgentRuntime,
    AgentRuntimeBlocked,
    AgentRuntimeRepository,
)

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
        llm_daily_request_limit=20,
        llm_daily_output_token_limit=3_000,
        llm_daily_cost_cap_usd=Decimal("1.00"),
    )


def _contract(workspace_id: UUID, owner_user_id: UUID, name: str) -> AgentContract:
    return AgentContract(
        agent_key="PROPERTY_RELEASE_FIXTURE",
        name=name,
        workspace_id=workspace_id,
        purpose="Return a cited property fixture summary without changing any data.",
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
        model_policy={"provider": "gemini", "max_output_tokens": 256},
        tool_keys=[],
        permission_keys=[],
        evidence_requirements=["synthetic fixture citation"],
        forbidden_actions=["Do not write, contact third parties, or change production."],
        kpis=[{"name": "fixture_response", "target": 1}],
        approval_required=True,
        timeout_seconds=120,
        prompt_template="Return a short cited fixture response. Do not take actions.",
    )


def _response() -> ModelResponse:
    return ModelResponse(
        provider="gemini",
        model="gemini-3.7-flash",
        output_text='{"summary":"Synthetic property result","citations":["FIXTURE-001"]}',
        usage=ModelUsage(input_tokens=10, output_tokens=10),
        latency_milliseconds=1,
        estimated_cost_usd=Decimal("0"),
    )


def _add_workspace_actor(
    connection: psycopg.Connection[object], organization_id: UUID, workspace_id: UUID, email: str
) -> UUID:
    user = connection.execute(
        """
        INSERT INTO identity.users (organization_id, email, display_name)
        VALUES (%s, %s, %s) RETURNING user_id
        """,
        (organization_id, email, email.split("@")[0]),
    ).fetchone()
    assert user is not None
    user_id = UUID(str(user[0]))
    connection.execute(
        """
        INSERT INTO workspace.memberships (workspace_id, user_id, access_level)
        VALUES (%s, %s, 'EDITOR')
        """,
        (workspace_id, user_id),
    )
    return user_id


def _complete_release(
    repository: ReleaseGovernanceRepository,
    runtime: AgentRuntime,
    *,
    organization_id: UUID,
    workspace_id: UUID,
    maker_user_id: UUID,
    checker_user_id: UUID,
    business_reviewer_id: UUID,
    technical_reviewer_id: UUID,
    approver_user_id: UUID,
) -> UUID:
    request = repository.create_release_request(
        "PROPERTY_RELEASE_FIXTURE",
        workspace_id,
        "Release a read-only synthetic fixture agent after independently recorded tests.",
        organization_id=organization_id,
        maker_user_id=maker_user_id,
        correlation_id=uuid4(),
    )
    with pytest.raises(LifecycleConflictError, match="release request already exists"):
        repository.create_release_request(
            "PROPERTY_RELEASE_FIXTURE",
            workspace_id,
            "A duplicate request for the same immutable draft version must be rejected.",
            organization_id=organization_id,
            maker_user_id=maker_user_id,
            correlation_id=uuid4(),
        )
    first_case = None
    for category in ("POSITIVE", "NEGATIVE", "REGRESSION", "SECURITY", "RECOVERY"):
        case = repository.register_test_case(
            request.change_request_id,
            ReleaseTestCaseRequest(
                test_key=f"FIXTURE_{category}",
                category=category,
                input_fixture={"input": {"query": f"{category.lower()} fixture"}},
                expected_assertions={"status": "SUCCEEDED"},
            ),
            actor_user_id=maker_user_id,
            correlation_id=uuid4(),
        )
        if first_case is None:
            first_case = case
    assert first_case is not None
    with pytest.raises(SegregationOfDutiesError, match="maker cannot act as checker"):
        repository.record_test_result(
            request.change_request_id,
            first_case,
            checker_user_id=maker_user_id,
            correlation_id=uuid4(),
            passed=True,
            agent_run_id=None,
            result={},
        )

    runtime_results = []

    def execute_fixture(agent_key: str, run_request: AgentRunRequest) -> AgentRunResult:
        result = runtime.execute(
            agent_key,
            run_request,
            organization_id=organization_id,
            actor_user_id=checker_user_id,
        )
        runtime_results.append(result)
        return result

    runner = AgentTestRunner(repository, execute_fixture)
    for category in ("POSITIVE", "NEGATIVE", "REGRESSION", "SECURITY", "RECOVERY"):
        result = runner.execute(
            request.change_request_id,
            f"FIXTURE_{category}",
            checker_user_id=checker_user_id,
        )
        assert result.status == "PASSED", runtime_results[-1]

    assert (
        repository.submit_for_review(
            request.change_request_id,
            checker_user_id=checker_user_id,
            correlation_id=uuid4(),
        ).state
        == "IN_REVIEW"
    )
    assert (
        repository.review(
            request.change_request_id,
            ReviewRequest(
                gate="BUSINESS",
                decision="APPROVED",
                notes="Business evidence accepted.",
            ),
            reviewer_user_id=business_reviewer_id,
            correlation_id=uuid4(),
        ).state
        == "IN_REVIEW"
    )
    with pytest.raises(SegregationOfDutiesError, match="multiple review gates"):
        repository.review(
            request.change_request_id,
            ReviewRequest(gate="TECHNICAL", decision="APPROVED", notes="Invalid second duty."),
            reviewer_user_id=business_reviewer_id,
            correlation_id=uuid4(),
        )
    repository.review(
        request.change_request_id,
        ReviewRequest(gate="TECHNICAL", decision="APPROVED", notes="Technical controls accepted."),
        reviewer_user_id=technical_reviewer_id,
        correlation_id=uuid4(),
    )
    assert (
        repository.approve(
            request.change_request_id,
            approver_user_id=approver_user_id,
            correlation_id=uuid4(),
        ).state
        == "APPROVED"
    )
    assert (
        repository.release(
            request.change_request_id,
            approver_user_id=approver_user_id,
            correlation_id=uuid4(),
        ).state
        == "RELEASED"
    )
    assert (
        repository.activate(
            request.change_request_id,
            approver_user_id=approver_user_id,
            correlation_id=uuid4(),
        ).state
        == "ACTIVE"
    )
    return request.change_request_id


def test_release_lifecycle_enforces_sod_kill_switch_and_rollback() -> None:
    base_url = psycopg_url(get_settings().database_url)
    database_name = f"alos_h4_release_{uuid4().hex}"
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
        with psycopg.connect(temporary_url) as connection:
            maker_user_id = _add_workspace_actor(
                connection,
                context.organization_id,
                context.workspace_id,
                "maker@alos.test",
            )
            checker_user_id = _add_workspace_actor(
                connection,
                context.organization_id,
                context.workspace_id,
                "checker@alos.test",
            )
            business_reviewer_id = _add_workspace_actor(
                connection,
                context.organization_id,
                context.workspace_id,
                "business@alos.test",
            )
            technical_reviewer_id = _add_workspace_actor(
                connection,
                context.organization_id,
                context.workspace_id,
                "technical@alos.test",
            )
            approver_user_id = _add_workspace_actor(
                connection,
                context.organization_id,
                context.workspace_id,
                "approver@alos.test",
            )
            connection.commit()

        registry.create_draft(
            _contract(context.workspace_id, maker_user_id, "Property Release Fixture V1"),
            organization_id=context.organization_id,
            actor_user_id=maker_user_id,
            correlation_id=uuid4(),
            reason="H4 governed release fixture version 1",
        )
        runtime = AgentRuntime(
            AgentRuntimeRepository(temporary_url, settings),
            GuardedModelGateway(
                    RetryingModelGateway(FakeModelGateway([_response()] * 12), max_retries=1),
                    settings,
                    UsageBudget(request_limit=12, output_token_limit=4_000),
                ),
                settings,
            )
        release_repository = ReleaseGovernanceRepository(temporary_url)
        local_team = release_repository.bootstrap_local_release_team(context.workspace_id, uuid4())
        assert {participant.duty for participant in local_team.participants} == {
            "MAKER",
            "CHECKER",
            "BUSINESS_REVIEWER",
            "TECHNICAL_REVIEWER",
            "APPROVER",
        }
        version_one_request = _complete_release(
            release_repository,
            runtime,
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            maker_user_id=maker_user_id,
            checker_user_id=checker_user_id,
            business_reviewer_id=business_reviewer_id,
            technical_reviewer_id=technical_reviewer_id,
            approver_user_id=approver_user_id,
        )
        with pytest.raises(ReleaseGovernanceError, match="workspace membership"):
            release_repository.require_workspace_actor(version_one_request, uuid4())

        registry.update_draft(
            _contract(context.workspace_id, maker_user_id, "Property Release Fixture V2"),
            organization_id=context.organization_id,
            actor_user_id=maker_user_id,
            correlation_id=uuid4(),
            reason="H4 governed release fixture version 2",
        )
        version_two_request = _complete_release(
            release_repository,
            runtime,
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            maker_user_id=maker_user_id,
            checker_user_id=checker_user_id,
            business_reviewer_id=business_reviewer_id,
            technical_reviewer_id=technical_reviewer_id,
            approver_user_id=approver_user_id,
        )

        detail = release_repository.get_release_request_detail(
            version_two_request,
            organization_id=context.organization_id,
            actor_user_id=checker_user_id,
        )
        assert detail.state == "ACTIVE"
        assert len(detail.test_cases) == 5
        assert len(detail.test_runs) == 5
        assert {event.to_state for event in detail.lifecycle_events} >= {
            "DRAFT",
            "TESTED",
            "IN_REVIEW",
            "APPROVED",
            "RELEASED",
            "ACTIVE",
        }
        assert release_repository.list_release_requests(
            context.workspace_id,
            organization_id=context.organization_id,
            actor_user_id=checker_user_id,
        )[0].change_request_id == version_two_request

        assert (
            release_repository.kill_switch(
                version_two_request,
                actor_user_id=approver_user_id,
                reason="Controlled H4 kill-switch verification.",
                correlation_id=uuid4(),
            ).state
            == "SUSPENDED"
        )
        registry.update_draft(
            _contract(context.workspace_id, maker_user_id, "Property Release Fixture V3"),
            organization_id=context.organization_id,
            actor_user_id=maker_user_id,
            correlation_id=uuid4(),
            reason="Verify that the contract kill switch blocks a new draft fixture run.",
        )
        with pytest.raises(AgentRuntimeBlocked, match="kill switch is active"):
            runtime.execute(
                "PROPERTY_RELEASE_FIXTURE",
                AgentRunRequest(
                    workspace_id=context.workspace_id,
                    input={"query": "this draft must be blocked"},
                ),
                organization_id=context.organization_id,
                actor_user_id=checker_user_id,
            )
        with pytest.raises(LifecycleConflictError, match="clear the active kill switch"):
            release_repository.rollback(
                version_two_request,
                RollbackRequest(
                    target_semantic_version="0.1.0",
                    reason="Rollback must wait for an explicit kill-switch clear.",
                ),
                actor_user_id=approver_user_id,
                correlation_id=uuid4(),
            )
        assert (
            release_repository.clear_kill_switch(
                version_two_request,
                actor_user_id=approver_user_id,
                reason="Remediation verification completed.",
                correlation_id=uuid4(),
            ).state
            == "SUSPENDED"
        )
        assert (
            release_repository.rollback(
                version_two_request,
                RollbackRequest(
                    target_semantic_version="0.1.0",
                    reason="Return to the previously released fixture version.",
                ),
                actor_user_id=approver_user_id,
                correlation_id=uuid4(),
            ).state
            == "ROLLED_BACK"
        )
        with psycopg.connect(temporary_url) as connection:
            connection.execute(
                """
                UPDATE agents.versions SET lifecycle_status = 'RETIRED'
                WHERE agent_contract_id = (
                    SELECT agent_contract_id FROM agents.contracts
                    WHERE agent_key = 'PROPERTY_RELEASE_FIXTURE'
                ) AND semantic_version = '0.3.0'
                """
            )
            connection.commit()
        active_run = runtime.execute(
            "PROPERTY_RELEASE_FIXTURE",
            AgentRunRequest(
                workspace_id=context.workspace_id,
                input={"query": "run the locally active version"},
            ),
            organization_id=context.organization_id,
            actor_user_id=checker_user_id,
        )
        assert active_run.status == "SUCCEEDED"
        assert active_run.semantic_version == "0.1.0"

        with psycopg.connect(temporary_url) as connection:
            active = connection.execute(
                """
                SELECT version.semantic_version FROM agents.registry AS registry
                JOIN agents.versions AS version
                  ON version.agent_version_id = registry.active_version_id
                WHERE registry.agent_contract_id = (
                    SELECT agent_contract_id FROM agents.contracts
                    WHERE agent_key = 'PROPERTY_RELEASE_FIXTURE'
                )
                """
            ).fetchone()
            assert active == ("0.1.0",)
            transitions = connection.execute(
                """
                SELECT to_state FROM governance.agent_lifecycle_events
                WHERE change_request_id = %s
                ORDER BY event_sequence
                """,
                (version_two_request,),
            ).fetchall()
            assert [row[0] for row in transitions] == [
                "DRAFT",
                "TESTED",
                "IN_REVIEW",
                "APPROVED",
                "RELEASED",
                "ACTIVE",
                "SUSPENDED",
                "ROLLED_BACK",
            ]
            audit_actions = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT action FROM audit.events
                    WHERE action IN (
                        'KILL_SWITCH_ACTIVATED', 'KILL_SWITCH_CLEARED', 'AGENT_ROLLED_BACK'
                    )
                    """
                ).fetchall()
            }
            assert audit_actions == {
                "KILL_SWITCH_ACTIVATED",
                "KILL_SWITCH_CLEARED",
                "AGENT_ROLLED_BACK",
            }
            assert connection.execute(
                "SELECT action FROM audit.events WHERE action = 'LOCAL_RELEASE_TEAM_BOOTSTRAPPED'"
            ).fetchone() == ("LOCAL_RELEASE_TEAM_BOOTSTRAPPED",)
        assert version_one_request != version_two_request
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
