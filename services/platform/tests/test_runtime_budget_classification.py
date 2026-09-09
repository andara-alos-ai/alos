from decimal import Decimal
from uuid import UUID, uuid4

from alos.agents.registry import AgentContract
from alos.config import Settings
from alos.model_gateway import FakeModelGateway, GuardedModelGateway, UsageBudget
from alos.runtime.service import (
    AgentRunRequest,
    AgentRuntime,
    ToolDecision,
    _ExecutionVersion,
    _PreparedRun,
)


class PreparedRunRepository:
    """Minimal repository double that proves a gateway budget is a blocked run."""

    def __init__(self, prepared: _PreparedRun) -> None:
        self.prepared = prepared
        self.blocked: tuple[_PreparedRun, str, str] | None = None

    def prepare_run(self, *args: object, **kwargs: object) -> _PreparedRun:
        return self.prepared

    def complete_blocked(self, prepared: _PreparedRun, *, reason: str, tool_key: str) -> None:
        self.blocked = (prepared, reason, tool_key)


def test_in_memory_request_limit_is_persisted_as_a_blocked_run() -> None:
    organization_id, workspace_id, user_id = uuid4(), uuid4(), uuid4()
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql://unused/alos",
        auth_signing_secret="a" * 32,
        llm_provider="openai",
        llm_api_key="test-only-key",
        llm_model="gpt-5.6-luna",
        llm_model_light="gpt-5.6-luna",
        llm_model_standard="gpt-5.6-terra",
        llm_model_critical="gpt-5.6-sol",
        llm_max_output_tokens=300,
        llm_daily_request_limit=2,
        llm_daily_output_token_limit=1_000,
        llm_daily_cost_cap_usd=Decimal("1.00"),
    )
    prepared = _prepared_run(organization_id, workspace_id, user_id)
    repository = PreparedRunRepository(prepared)
    delegate = FakeModelGateway()
    runtime = AgentRuntime(
        repository,  # type: ignore[arg-type]
        GuardedModelGateway(
            delegate,
            settings,
            UsageBudget(request_limit=0, output_token_limit=300),
        ),
        settings,
    )

    result = runtime.execute(
        "UAT09_RUNTIME",
        AgentRunRequest(workspace_id=workspace_id, input={"query": "budget"}),
        organization_id=organization_id,
        actor_user_id=user_id,
    )

    assert result.status == "BLOCKED"
    assert result.error_code == "REQUEST_LIMIT"
    assert result.tool_decisions == [
        ToolDecision(
            tool_key="BUDGET_POLICY",
            decision="BLOCKED",
            reason="model request limit reached",
        )
    ]
    assert repository.blocked == (prepared, "model request limit reached", "BUDGET_POLICY")
    assert delegate.requests == []


def _prepared_run(organization_id: UUID, workspace_id: UUID, user_id: UUID) -> _PreparedRun:
    contract = AgentContract(
        agent_key="UAT09_RUNTIME",
        name="UAT-09 Runtime",
        workspace_id=workspace_id,
        purpose="Prove that an in-memory budget refusal is recorded as BLOCKED.",
        risk_level="LOW",
        owner_user_id=user_id,
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        model_policy={"max_output_tokens": 300},
        tool_keys=[],
        permission_keys=[],
        evidence_requirements=[],
        forbidden_actions=["No write."],
        kpis=[],
        approval_required=True,
        timeout_seconds=30,
        prompt_template="Return JSON only.",
    )
    return _PreparedRun(
        agent_run_id=uuid4(),
        execution=_ExecutionVersion(
            agent_contract_id=uuid4(),
            agent_version_id=uuid4(),
            agent_key=contract.agent_key,
            semantic_version="0.1.0",
            contract=contract,
        ),
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        correlation_id=uuid4(),
        input_hash="fixture-input-hash",
        tool_decisions=(),
        fixture_context=(),
    )
