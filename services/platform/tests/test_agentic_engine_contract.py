from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from alos.runtime.agentic import (
    AgenticExecutionEngine,
    AgenticExecutionRequest,
    AgenticExecutionResult,
    CumulativeUsage,
    ExecutionContext,
    ExecutionLimits,
    ExecutionMode,
    ExecutionStatus,
)


class RecordingEngine:
    def __init__(self) -> None:
        self.requests: list[AgenticExecutionRequest] = []
        self.cancelled: list[UUID] = []

    def execute(self, request: AgenticExecutionRequest) -> AgenticExecutionResult:
        self.requests.append(request)
        return AgenticExecutionResult(
            run_id=request.context.run_id,
            correlation_id=request.context.correlation_id,
            status=ExecutionStatus.SUCCEEDED,
            output={"result": "bounded"},
        )

    def cancel(self, run_id: UUID) -> bool:
        self.cancelled.append(run_id)
        return True


def context() -> ExecutionContext:
    return ExecutionContext(
        organization_id=uuid4(),
        workspace_id=uuid4(),
        division_id=uuid4(),
        project_id=uuid4(),
        tenant_id=uuid4(),
        actor_user_id=uuid4(),
        actor_role="OPERATOR",
        agent_id=uuid4(),
        agent_version_id=uuid4(),
        run_id=uuid4(),
        correlation_id=uuid4(),
        execution_mode=ExecutionMode.TEST,
        classification="INTERNAL",
    )


def test_framework_neutral_engine_protocol_is_structurally_implemented() -> None:
    engine = RecordingEngine()
    request = AgenticExecutionRequest(
        context=context(),
        instructions="Return a structured result.",
        input_text="Synthetic input",
        output_schema={"type": "object"},
        limits=ExecutionLimits(),
    )

    assert isinstance(engine, AgenticExecutionEngine)
    result = engine.execute(request)
    assert result.output == {"result": "bounded"}
    assert engine.cancel(request.context.run_id)


def test_execution_limits_reject_an_inconsistent_token_envelope() -> None:
    with pytest.raises(ValidationError, match="max_total_tokens"):
        ExecutionLimits(
            max_input_tokens=100,
            max_output_tokens=50,
            max_total_tokens=149,
        )


def test_execution_limits_reject_run_cost_above_daily_cost() -> None:
    with pytest.raises(ValidationError, match="max_cost_per_run"):
        ExecutionLimits(
            max_cost_per_run=Decimal("6"),
            daily_agent_cost_limit=Decimal("5"),
        )


def test_cumulative_usage_requires_exact_token_accounting() -> None:
    with pytest.raises(ValidationError, match="total_tokens"):
        CumulativeUsage(
            total_input_tokens=10,
            total_output_tokens=5,
            total_tokens=14,
        )


def test_failed_result_requires_a_safe_error_code() -> None:
    execution_context = context()
    with pytest.raises(ValidationError, match="error_code"):
        AgenticExecutionResult(
            run_id=execution_context.run_id,
            correlation_id=execution_context.correlation_id,
            status=ExecutionStatus.BLOCKED,
        )
