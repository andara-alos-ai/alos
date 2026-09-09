import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from alos.agents.registry import AgentContract
from alos.config import Settings
from alos.identity import DataScope, HumanRole
from alos.model_gateway import FakeModelGateway, ModelResponse, ModelUsage
from alos.runtime.service import (
    AgentRunRequest,
    AgentRunResult,
    AgentRuntime,
    ToolDecision,
    _ExecutionVersion,
    _PreparedRun,
)
from alos.security.tokens import ActorContext


class PreparedAgenticRepository:
    database_url = "postgresql://unused/alos"

    def __init__(self, prepared: _PreparedRun) -> None:
        self.prepared = prepared
        self.steps: list[tuple[str, dict[str, Any]]] = []
        self.success: tuple[ModelResponse, dict[str, Any], int, int] | None = None
        self.blocked: tuple[str, str] | None = None

    def prepare_run(self, *args: object, **kwargs: object) -> _PreparedRun:
        return self.prepared

    def load_agentic_tools(self, execution: _ExecutionVersion) -> list[object]:
        return []

    def record_step(
        self, prepared: _PreparedRun, step_type: str, content: dict[str, Any]
    ) -> None:
        self.steps.append((step_type, content))

    def complete_success(
        self,
        prepared: _PreparedRun,
        response: ModelResponse,
        output: dict[str, Any],
        *,
        model_calls: int = 1,
        tool_calls: int = 0,
    ) -> None:
        self.success = (response, output, model_calls, tool_calls)

    def complete_blocked(
        self, prepared: _PreparedRun, *, reason: str, tool_key: str
    ) -> None:
        self.blocked = (reason, tool_key)


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql://unused/alos",
        auth_signing_secret="a" * 32,
        llm_provider="openai",
        llm_api_key="test-key",
        llm_model="gpt-5.6-luna",
        llm_model_standard="gpt-5.6-terra",
    )


def prepared_run() -> _PreparedRun:
    workspace_id, owner_id = uuid4(), uuid4()
    contract = AgentContract(
        agent_key="GENERIC_MONITOR",
        name="Generic Monitor",
        workspace_id=workspace_id,
        purpose="Exercise the PydanticAI runtime through the public facade.",
        risk_level="LOW",
        owner_user_id=owner_id,
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        },
        model_policy={"execution_engine": "PYDANTICAI", "model_route": "standard"},
        tool_keys=[],
        permission_keys=[],
        evidence_requirements=["Use approved evidence."],
        forbidden_actions=["No unapproved material action."],
        kpis=[{"key": "bounded"}],
        approval_required=True,
        timeout_seconds=30,
        prompt_template="Return a governed result.",
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
        organization_id=uuid4(),
        workspace_id=workspace_id,
        actor_user_id=owner_id,
        correlation_id=uuid4(),
        input_hash="input-hash",
        tool_decisions=(),
        fixture_context=(),
        execution_mode="TEST",
    )


def actor(prepared: _PreparedRun) -> ActorContext:
    now = datetime.now(UTC)
    return ActorContext(
        user_id=prepared.actor_user_id,
        organization_id=prepared.organization_id,
        roles=[HumanRole.DIRECTOR],
        workspace_ids=[prepared.workspace_id],
        data_scope=DataScope.COMPANY,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def gateway() -> FakeModelGateway:
    return FakeModelGateway(
        [
            ModelResponse(
                provider="fake",
                model="gpt-5.6-terra",
                output_text=json.dumps(
                    {"type": "final", "output": {"result": "agentic"}}
                ),
                usage=ModelUsage(input_tokens=10, output_tokens=5),
                latency_milliseconds=3,
                estimated_cost_usd=Decimal("0.001"),
            )
        ]
    )


def test_public_runtime_facade_uses_agentic_engine_for_opted_in_contract() -> None:
    prepared = prepared_run()
    repository = PreparedAgenticRepository(prepared)
    runtime = AgentRuntime(repository, gateway(), settings())  # type: ignore[arg-type]

    result = runtime.execute(
        prepared.execution.agent_key,
        AgentRunRequest(workspace_id=prepared.workspace_id, input={"record": "R-1"}),
        organization_id=prepared.organization_id,
        actor_user_id=prepared.actor_user_id,
        actor=actor(prepared),
    )

    assert result.status == "SUCCEEDED"
    assert result.output == {"result": "agentic"}
    assert result.total_model_calls == 1
    assert result.total_tokens == 15
    assert repository.success is not None
    assert repository.success[2:] == (1, 0)
    assert any(step_type == "AGENTIC_FINAL" for step_type, _ in repository.steps)


def test_agentic_contract_without_actor_is_blocked_before_model_call() -> None:
    prepared = prepared_run()
    repository = PreparedAgenticRepository(prepared)
    model_gateway = gateway()
    runtime = AgentRuntime(repository, model_gateway, settings())  # type: ignore[arg-type]

    result: AgentRunResult = runtime.execute(
        prepared.execution.agent_key,
        AgentRunRequest(workspace_id=prepared.workspace_id),
        organization_id=prepared.organization_id,
        actor_user_id=prepared.actor_user_id,
    )

    assert result.status == "BLOCKED"
    assert result.error_code == "ACTOR_CONTEXT_REQUIRED"
    assert repository.blocked is not None
    assert model_gateway.requests == []
    assert result.tool_decisions == [
        ToolDecision(
            tool_key="ACTOR_CONTEXT",
            decision="BLOCKED",
            reason="agentic execution requires an authenticated actor context",
        )
    ]
